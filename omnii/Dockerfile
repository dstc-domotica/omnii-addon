ARG BUILD_FROM
FROM $BUILD_FROM AS builder

RUN apk add --no-cache python3 py3-pip gcc g++ musl-dev

COPY requirements.txt /
RUN pip3 install --no-cache-dir --break-system-packages -r /requirements.txt

COPY proto /proto
RUN mkdir -p /app/grpc_stubs && \
    python3 -m grpc_tools.protoc -I/proto --python_out=/app/grpc_stubs --grpc_python_out=/app/grpc_stubs /proto/omnnii.proto && \
    touch /app/grpc_stubs/__init__.py

FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip

COPY --from=builder /app/grpc_stubs /app/grpc_stubs
COPY requirements.txt /
RUN pip3 install --no-cache-dir --break-system-packages --upgrade pip && \
    pip3 install --no-cache-dir --break-system-packages -r /requirements.txt

COPY run.sh /
COPY omnii_addon.py /
COPY omnii_connector /app/omnii_connector
COPY proto /proto
RUN chmod a+x /run.sh /omnii_addon.py

# Ensure generated gRPC stubs are on the module search path
ENV PYTHONPATH=/app/grpc_stubs:/app:$PYTHONPATH
WORKDIR /app

CMD [ "/run.sh" ]
