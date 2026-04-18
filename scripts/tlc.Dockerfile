# TLC (TLA+ model checker) image.
# Builds a small JRE + tla2tools.jar bundle for reproducible model-checking.
FROM eclipse-temurin:21-jre

ARG TLA_VERSION=1.8.0
ADD https://github.com/tlaplus/tlaplus/releases/download/v${TLA_VERSION}/tla2tools.jar /opt/tla/tla2tools.jar

ENTRYPOINT ["java", "-XX:+UseParallelGC", "-jar", "/opt/tla/tla2tools.jar"]
