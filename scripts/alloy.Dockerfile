# Alloy Analyzer image.
# Builds a small JRE + Alloy dist jar bundle for reproducible model finding.
FROM eclipse-temurin:21-jre

ARG ALLOY_VERSION=6.2.0
# Pinned checksum for org.alloytools.alloy.dist 6.2.0 from Maven Central, so
# local builds resolve to the same binary. Bump this alongside ALLOY_VERSION.
# Requires BuildKit >= 1.6.
ADD --checksum=sha256:6037cbeee0e8423c1c468447ed10f5fcf2f2743a2ffc39cb1c81f2905c0fdb9d \
    https://repo1.maven.org/maven2/org/alloytools/org.alloytools.alloy.dist/${ALLOY_VERSION}/org.alloytools.alloy.dist-${ALLOY_VERSION}.jar \
    /opt/alloy/alloy.jar

ENTRYPOINT ["java", "--enable-native-access=ALL-UNNAMED", "-jar", "/opt/alloy/alloy.jar"]
