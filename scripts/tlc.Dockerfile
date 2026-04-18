# TLC (TLA+ model checker) image.
# Builds a small JRE + tla2tools.jar bundle for reproducible model-checking.
FROM eclipse-temurin:21-jre

ARG TLA_VERSION=1.8.0
# No checksum verification: Docker ADD over HTTPS does not validate integrity by default.
# Before promoting to CI, pin with: ADD --checksum sha256:<hash> <url> /opt/tla/tla2tools.jar
# (requires BuildKit >= 1.6). Acceptable for a research PoC; not for a gated job.
ADD https://github.com/tlaplus/tlaplus/releases/download/v${TLA_VERSION}/tla2tools.jar /opt/tla/tla2tools.jar

ENTRYPOINT ["java", "-XX:+UseParallelGC", "-jar", "/opt/tla/tla2tools.jar"]
