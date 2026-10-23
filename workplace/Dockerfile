FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY . .
RUN chmod +x gradlew && ./gradlew --no-daemon :app:installDist

FROM eclipse-temurin:21-jre-jammy
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/auth
COPY --from=build /src/app/build/install/app/ ./
EXPOSE 8080
ENTRYPOINT ["/opt/auth/bin/app"]
