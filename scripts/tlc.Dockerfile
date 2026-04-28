# TLC (TLA+ model checker) image.
# Builds a small JRE + tla2tools.jar bundle for reproducible model-checking.
FROM eclipse-temurin:21-jre

ARG TLA_VERSION=1.7.4
# Pinned checksum for tla2tools.jar v1.7.4 so local and CI builds resolve to
# the same binary. Bump this alongside TLA_VERSION. Requires BuildKit >= 1.6.
ADD --checksum=sha256:936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88 \
    https://github.com/tlaplus/tlaplus/releases/download/v${TLA_VERSION}/tla2tools.jar \
    /opt/tla/tla2tools.jar

ENTRYPOINT ["java", "-XX:+UseParallelGC", "-jar", "/opt/tla/tla2tools.jar"]
