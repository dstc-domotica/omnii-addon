import base64
import socket
import ssl
import threading
import time
from typing import Dict, Optional, Sequence, Tuple

import grpc

from grpc_stubs import omnnii_pb2, omnnii_pb2_grpc

from .constants import (
    HEARTBEAT_INTERVAL_SECONDS,
    STATS_REPORT_INTERVAL_SECONDS,
    UPDATE_REPORT_INTERVAL_SECONDS,
)
from .enrollment_store import load_enrollment_data, save_enrollment_data
from .supervisor_api import SupervisorClient


class OmniiGrpcClient:
    def __init__(
        self,
        server_url: str,
        enrollment_code: str,
        tls_skip_verify: bool = False,
        tls_ca_cert: Optional[str] = None,
    ):
        # server_url is the gRPC server address (e.g., "192.168.1.100:50051")
        self.server_url = server_url.rstrip("/")
        self.enrollment_code = enrollment_code

        self.enrollment_data: Optional[Dict] = None
        self.channel: Optional[grpc.Channel] = None
        self.stub: Optional[omnnii_pb2_grpc.OmniiServiceStub] = None
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.access_token_expires_at: Optional[int] = None
        self.tls_skip_verify = tls_skip_verify
        self.tls_ca_cert = tls_ca_cert

        self.running = False
        self.start_time = time.time()
        self.heartbeat_timer: Optional[threading.Timer] = None
        self.update_report_timer: Optional[threading.Timer] = None
        self.stats_report_timer: Optional[threading.Timer] = None
        self.last_full_info_time: float = 0

        self.supervisor = SupervisorClient()

    def load_existing_enrollment(self) -> bool:
        self.enrollment_data = load_enrollment_data()
        return self.enrollment_data is not None

    def _create_channel(self, server_url: str) -> grpc.Channel:
        root_certificates = None
        if self.tls_ca_cert:
            try:
                with open(self.tls_ca_cert, "rb") as cert_file:
                    root_certificates = cert_file.read()
            except Exception as e:
                print(f"Failed to read TLS CA cert: {e}")
                raise

        options: Sequence[Tuple[str, str]] = []

        if self.tls_skip_verify:
            if not self.tls_ca_cert:
                # Fetch the server's certificate and use it directly to skip verification
                # This trusts the certificate presented by the server without CA validation
                host, port_str = server_url.rsplit(":", 1)
                port = int(port_str)

                try:
                    # Create an unverified SSL context to fetch the server's certificate
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE

                    with socket.create_connection((host, port), timeout=10) as sock:
                        with context.wrap_socket(sock, server_hostname=host) as ssock:
                            der_cert = ssock.getpeercert(binary_form=True)
                            if der_cert:
                                # Convert DER to PEM format
                                pem_cert = (
                                    b"-----BEGIN CERTIFICATE-----\n"
                                    + base64.encodebytes(der_cert)
                                    + b"-----END CERTIFICATE-----\n"
                                )
                                root_certificates = pem_cert
                                print("TLS verification skipped: using server's certificate directly")
                except Exception as e:
                    print(f"Warning: Could not fetch server certificate: {e}")
                    print("Falling back to insecure channel (no TLS)")
                    return grpc.insecure_channel(server_url)

            options = [
                ("grpc.ssl_target_name_override", "omnii-grpc"),
                ("grpc.default_authority", "omnii-grpc"),
            ]

        credentials = grpc.ssl_channel_credentials(root_certificates=root_certificates)
        return grpc.secure_channel(server_url, credentials, options=options)

    def enroll(self) -> bool:
        """Enroll with the server via gRPC."""
        try:
            print(f"Enrolling with gRPC server at {self.server_url}...")

            channel = self._create_channel(self.server_url)
            stub = omnnii_pb2_grpc.OmniiServiceStub(channel)

            response = stub.Enroll(
                omnnii_pb2.EnrollRequest(code=self.enrollment_code),
                timeout=10,
            )

            if response.success:
                self.enrollment_data = {
                    "instanceId": response.instance_id,
                    "accessToken": response.access_token,
                    "refreshToken": response.refresh_token,
                    "accessTokenExpiresAt": response.access_token_expires_at,
                    "grpcServerUrl": self.server_url,
                }
                print(f"Enrolled successfully. Instance ID: {response.instance_id}")
                save_enrollment_data(self.enrollment_data)
                return True

            print(f"Enrollment failed: {response.error}")
            return False
        except grpc.RpcError as e:
            print(f"gRPC Enrollment error: {e.code()}: {e.details()}")
            return False
        except Exception as e:
            print(f"Enrollment error: {e}")
            return False

    def connect_and_handshake(self) -> bool:
        """Connect to the gRPC server and prepare authenticated calls."""
        if not self.enrollment_data:
            print("Not enrolled. Call enroll() first.")
            return False

        grpc_url = self.enrollment_data.get("grpcServerUrl", self.server_url)
        print(f"Connecting to gRPC server at {grpc_url}...")

        self.channel = self._create_channel(grpc_url)
        self.stub = omnnii_pb2_grpc.OmniiServiceStub(self.channel)

        self.access_token = self.enrollment_data.get("accessToken")
        self.refresh_token = self.enrollment_data.get("refreshToken")
        self.access_token_expires_at = self.enrollment_data.get(
            "accessTokenExpiresAt"
        )

        if not self.refresh_token:
            print("Missing refresh token. Please re-enroll.")
            return False

        if not self._ensure_access_token():
            print("Failed to refresh access token.")
            return False

        self.running = True
        return True

    def _token_expired(self) -> bool:
        if not self.access_token_expires_at:
            return True
        return int(time.time()) >= int(self.access_token_expires_at) - 30

    def _auth_metadata(self) -> list:
        return [("authorization", f"Bearer {self.access_token}")]

    def _ensure_access_token(self) -> bool:
        if not self.access_token or self._token_expired():
            return self.refresh_access_token()
        return True

    def refresh_access_token(self) -> bool:
        if not self.stub or not self.refresh_token:
            return False

        try:
            response = self.stub.RefreshToken(
                omnnii_pb2.RefreshTokenRequest(refresh_token=self.refresh_token),
                timeout=10,
            )
            if response.success:
                self.access_token = response.access_token
                if response.refresh_token:
                    self.refresh_token = response.refresh_token
                self.access_token_expires_at = response.access_token_expires_at
                if self.enrollment_data is not None:
                    self.enrollment_data.update(
                        {
                            "accessToken": self.access_token,
                            "refreshToken": self.refresh_token,
                            "accessTokenExpiresAt": self.access_token_expires_at,
                        }
                    )
                    save_enrollment_data(self.enrollment_data)
                return True

            print(f"Refresh token failed: {response.error}")
            return False
        except grpc.RpcError as e:
            print(f"Refresh token error: {e.code()}: {e.details()}")
            return False

    def _call_with_auth(self, rpc, request, timeout: int):
        if not self._ensure_access_token():
            raise RuntimeError("Access token unavailable")

        metadata = self._auth_metadata()
        try:
            return rpc(request, timeout=timeout, metadata=metadata)
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNAUTHENTICATED:
                if self.refresh_access_token():
                    metadata = self._auth_metadata()
                    return rpc(request, timeout=timeout, metadata=metadata)
            raise

    def start_heartbeat(self) -> None:
        if not self.running:
            return
        print(
            f"Starting heartbeat thread ({HEARTBEAT_INTERVAL_SECONDS} second interval)..."
        )
        self.send_heartbeat(include_full_info=True)
        self._schedule_heartbeat()
        self.start_update_reporting()
        self.start_stats_reporting()

    def _schedule_heartbeat(self) -> None:
        if not self.running:
            return
        self.heartbeat_timer = threading.Timer(
            float(HEARTBEAT_INTERVAL_SECONDS), self._heartbeat_loop
        )
        self.heartbeat_timer.daemon = True
        self.heartbeat_timer.start()

    def _heartbeat_loop(self) -> None:
        if not self.running:
            return

        include_full_info = (time.time() - self.last_full_info_time) >= 300
        self.send_heartbeat(include_full_info=include_full_info)

        if self.running:
            self._schedule_heartbeat()

    def send_heartbeat(self, include_full_info: bool = False) -> None:
        if not self.running or not self.stub:
            return

        try:
            client_timestamp = int(time.time() * 1000)
            request = omnnii_pb2.HeartbeatRequest(client_timestamp=client_timestamp)

            if include_full_info:
                supervisor_info = self.supervisor.get_info()
                if supervisor_info:
                    system_info = omnnii_pb2.SystemInfo(
                        supervisor=supervisor_info.get("supervisor", ""),
                        homeassistant=supervisor_info.get("homeassistant", ""),
                        hassos=supervisor_info.get("hassos", "") or "",
                        docker=supervisor_info.get("docker", ""),
                        hostname=supervisor_info.get("hostname", ""),
                        operating_system=supervisor_info.get("operating_system", ""),
                        machine=supervisor_info.get("machine", ""),
                        arch=supervisor_info.get("arch", ""),
                        channel=supervisor_info.get("channel", ""),
                        state=supervisor_info.get("state", ""),
                    )
                    request.system_info.CopyFrom(system_info)

                self.last_full_info_time = time.time()
                print("Heartbeat sent with full system info")
            else:
                print("Heartbeat sent (minimal)")

            response = self._call_with_auth(self.stub.Heartbeat, request, timeout=10)

            if not response.alive:
                print("Server indicated session is not alive, reconnecting...")
                self.running = False
            elif response.latency_ms > 0:
                print(f"Latency: {response.latency_ms}ms")

        except grpc.RpcError as e:
            print(f"Heartbeat failed: {e.code()}: {e.details()}")
        except Exception as e:
            print(f"Heartbeat failed: {e}")

    def start_update_reporting(self) -> None:
        if not self.running:
            return
        print(
            f"Starting update reporting thread ({UPDATE_REPORT_INTERVAL_SECONDS} second interval)..."
        )
        self.send_update_report()
        self._schedule_update_report()

    def _schedule_update_report(self) -> None:
        if not self.running:
            return
        self.update_report_timer = threading.Timer(
            UPDATE_REPORT_INTERVAL_SECONDS, self._update_report_loop
        )
        self.update_report_timer.daemon = True
        self.update_report_timer.start()

    def _update_report_loop(self) -> None:
        if not self.running:
            return

        self.send_update_report()

        if self.running:
            self._schedule_update_report()

    def send_update_report(self) -> None:
        if not self.running or not self.stub:
            return

        try:
            components = self.supervisor.get_update_components()
            report = omnnii_pb2.UpdateReport(generated_at=int(time.time()))
            for component in components:
                report.components.append(
                    omnnii_pb2.ComponentUpdate(
                        component_type=component.get("component_type", ""),
                        slug=component.get("slug", ""),
                        name=component.get("name", ""),
                        version=component.get("version", ""),
                        version_latest=component.get("version_latest", ""),
                        update_available=bool(component.get("update_available")),
                    )
                )

            request = omnnii_pb2.UpdateReportRequest(report=report)
            response = self._call_with_auth(self.stub.ReportUpdates, request, timeout=15)

            if response.accepted:
                print(
                    f"Update report sent ({len(components)} components, accepted)"
                )
            else:
                print(f"Update report rejected: {response.message}")
        except grpc.RpcError as e:
            print(f"Update report failed: {e.code()}: {e.details()}")
        except Exception as e:
            print(f"Update report failed: {e}")

    def start_stats_reporting(self) -> None:
        if not self.running:
            return
        print(
            f"Starting core stats reporting thread ({STATS_REPORT_INTERVAL_SECONDS} second interval)..."
        )
        self.send_stats_report()
        self._schedule_stats_report()

    def _schedule_stats_report(self) -> None:
        if not self.running:
            return
        self.stats_report_timer = threading.Timer(
            STATS_REPORT_INTERVAL_SECONDS, self._stats_report_loop
        )
        self.stats_report_timer.daemon = True
        self.stats_report_timer.start()

    def _stats_report_loop(self) -> None:
        if not self.running:
            return

        self.send_stats_report()

        if self.running:
            self._schedule_stats_report()

    def send_stats_report(self) -> None:
        if not self.running or not self.stub:
            return

        try:
            stats = self.supervisor.get_core_stats()
            if not stats:
                print("Core stats unavailable; skipping stats report")
                return

            report = omnnii_pb2.StatsReport(generated_at=int(time.time()))
            report.stats.CopyFrom(
                omnnii_pb2.CoreStats(
                    cpu_percent=float(stats.get("cpu_percent") or 0.0),
                    memory_usage=int(stats.get("memory_usage") or 0),
                    memory_limit=int(stats.get("memory_limit") or 0),
                    memory_percent=float(stats.get("memory_percent") or 0.0),
                    network_tx=int(stats.get("network_tx") or 0),
                    network_rx=int(stats.get("network_rx") or 0),
                    blk_read=int(stats.get("blk_read") or 0),
                    blk_write=int(stats.get("blk_write") or 0),
                )
            )

            request = omnnii_pb2.StatsReportRequest(report=report)
            response = self._call_with_auth(self.stub.ReportStats, request, timeout=10)

            if response.accepted:
                print("Core stats report sent (accepted)")
            else:
                print(f"Core stats report rejected: {response.message}")
        except grpc.RpcError as e:
            print(f"Core stats report failed: {e.code()}: {e.details()}")
        except Exception as e:
            print(f"Core stats report failed: {e}")

    def stop(self) -> None:
        print("Stopping add-on...")
        self.running = False
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()
            self.heartbeat_timer = None
        if self.update_report_timer:
            self.update_report_timer.cancel()
            self.update_report_timer = None
        if self.stats_report_timer:
            self.stats_report_timer.cancel()
            self.stats_report_timer = None
        if self.channel:
            self.channel.close()
            self.channel = None

