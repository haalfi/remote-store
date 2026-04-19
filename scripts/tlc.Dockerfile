# TLC (TLA+ model checker) image.
# Builds a small JRE + tla2tools.jar bundle for reproducible model-checking.
FROM eclipse-temurin:21-jre

ARG TLA_VERSION=1.8.0
# Pinned checksum for tla2tools.jar v1.8.0 so local and CI builds resolve to
# the same binary. Bump this alongside TLA_VERSION. Requires BuildKit >= 1.6.
ADD --checksum=sha256:af03b2baae73b523fe162c0ff195c5adeed42cd1d092200b0bde2cd15914f624 \
    https://github.com/tlaplus/tlaplus/releases/download/v${TLA_VERSION}/tla2tools.jar \
    /opt/tla/tla2tools.jar

ENTRYPOINT ["java", "-XX:+UseParallelGC", "-jar", "/opt/tla/tla2tools.jar"]
