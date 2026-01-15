import threading
import time
from typing import Dict, Optional

import grpc

from grpc_stubs import omnnii_pb2, omnnii_pb2_grpc

from .constants import HEARTBEAT_INTERVAL_SECONDS, UPDATE_REPORT_INTERVAL_SECONDS
from .enrollment_store import load_enrollment_data, save_enrollment_data
from .supervisor_api import SupervisorClient


class OmniiGrpcClient:
    def __init__(self, server_url: str, enrollment_code: str):
        # server_url is the gRPC server address (e.g., "192.168.1.100:50051")
        self.server_url = server_url.rstrip("/")
        self.enrollment_code = enrollment_code

        self.enrollment_data: Optional[Dict] = None
        self.channel: Optional[grpc.Channel] = None
        self.stub: Optional[omnnii_pb2_grpc.OmniiServiceStub] = None
        self.session_id: Optional[str] = None

        self.running = False
        self.start_time = time.time()
        self.heartbeat_timer: Optional[threading.Timer] = None
        self.update_report_timer: Optional[threading.Timer] = None
        self.last_full_info_time: float = 0

        self.supervisor = SupervisorClient()

    def load_existing_enrollment(self) -> bool:
        self.enrollment_data = load_enrollment_data()
        return self.enrollment_data is not None

    def _create_channel(self) -> grpc.Channel:
        return grpc.insecure_channel(self.server_url)

    def enroll(self) -> bool:
        """Enroll with the server via gRPC."""
        try:
            print(f"Enrolling with gRPC server at {self.server_url}...")

            channel = self._create_channel()
            stub = omnnii_pb2_grpc.OmniiServiceStub(channel)

            response = stub.Enroll(
                omnnii_pb2.EnrollRequest(code=self.enrollment_code),
                timeout=10,
            )

            if response.success:
                self.enrollment_data = {
                    "instanceId": response.instance_id,
                    "token": response.token,
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
        """Connect to the gRPC server and perform handshake."""
        if not self.enrollment_data:
            print("Not enrolled. Call enroll() first.")
            return False

        grpc_url = self.enrollment_data.get("grpcServerUrl", self.server_url)
        print(f"Connecting to gRPC server at {grpc_url}...")

        self.channel = grpc.insecure_channel(grpc_url)
        self.stub = omnnii_pb2_grpc.OmniiServiceStub(self.channel)

        instance_id = self.enrollment_data.get("instanceId", "unknown")
        token = self.enrollment_data.get("token", "")

        try:
            response = self.stub.Handshake(
                omnnii_pb2.HandshakeRequest(addon_id=instance_id, token=token),
                timeout=10,
            )

            if response.status == "ok":
                self.session_id = response.session_id
                print(f"Handshake completed. Session ID: {self.session_id[:16]}...")
                self.running = True
                return True

            print(f"Handshake failed: {response.status}")
            return False
        except grpc.RpcError as e:
            print(f"gRPC Handshake failed: {e.code()}: {e.details()}")
            return False

    def start_heartbeat(self) -> None:
        if not self.running:
            return
        print(
            f"Starting heartbeat thread ({HEARTBEAT_INTERVAL_SECONDS} second interval)..."
        )
        self.send_heartbeat(include_full_info=True)
        self._schedule_heartbeat()
        self.start_update_reporting()

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
        if not self.running or not self.session_id or not self.stub:
            return

        try:
            client_timestamp = int(time.time() * 1000)
            request = omnnii_pb2.HeartbeatRequest(
                session_id=self.session_id, client_timestamp=client_timestamp
            )

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

            response = self.stub.Heartbeat(request, timeout=10)

            if not response.alive:
                print("Server indicated session is not alive, reconnecting...")
                self.running = False
            elif response.latency_ms > 0:
                print(f"Latency: {response.latency_ms}ms")

        except grpc.RpcError as e:
            print(f"Heartbeat failed: {e.code()}: {e.details()}")

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
        if not self.running or not self.session_id or not self.stub:
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

            request = omnnii_pb2.UpdateReportRequest(
                session_id=self.session_id, report=report
            )
            response = self.stub.ReportUpdates(request, timeout=15)

            if response.accepted:
                print(
                    f"Update report sent ({len(components)} components, accepted)"
                )
            else:
                print(f"Update report rejected: {response.message}")
        except grpc.RpcError as e:
            print(f"Update report failed: {e.code()}: {e.details()}")

    def stop(self) -> None:
        print("Stopping add-on...")
        self.running = False
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()
            self.heartbeat_timer = None
        if self.update_report_timer:
            self.update_report_timer.cancel()
            self.update_report_timer = None
        if self.channel:
            self.channel.close()
            self.channel = None

