# --- build stage: compile the Spring app and vendor the exact tracer version ---
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
RUN mvn -q -B -DskipTests package
# Pin dd-java-agent to 1.64.2 (same version used in the earlier local tracer run).
RUN mvn -q -B org.apache.maven.plugins:maven-dependency-plugin:3.6.1:copy \
    -Dartifact=com.datadoghq:dd-java-agent:1.64.2 \
    -DoutputDirectory=/agent

# --- runtime stage ---
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /build/target/identity-proxy.jar /app/app.jar
COPY --from=build /agent/dd-java-agent-1.64.2.jar /app/dd-java-agent.jar

ARG DD_GIT_REPOSITORY_URL
ARG DD_GIT_COMMIT_SHA
ENV DD_GIT_REPOSITORY_URL=${DD_GIT_REPOSITORY_URL}
ENV DD_GIT_COMMIT_SHA=${DD_GIT_COMMIT_SHA}

EXPOSE 8080
ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -javaagent:/app/dd-java-agent.jar -jar /app/app.jar"]
