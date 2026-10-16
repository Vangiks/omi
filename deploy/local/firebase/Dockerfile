# Firestore and Auth emulators for deploy/local. Build context is the repo root
# so the image carries the same rules and indexes as `make dev-up`.
FROM node:22-trixie-slim

ARG FIREBASE_TOOLS_VERSION
RUN test -n "$FIREBASE_TOOLS_VERSION" \
    && apt-get update \
    && apt-get install -y --no-install-recommends openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g "firebase-tools@${FIREBASE_TOOLS_VERSION}" \
    && npm cache clean --force

WORKDIR /app
# Download the Firestore emulator jar at build time, not on every start.
RUN firebase setup:emulators:firestore

COPY firestore.rules firestore.indexes.json ./
COPY deploy/local/firebase/firebase.json deploy/local/firebase/entrypoint.sh ./

ENV FIREBASE_PROJECT=demo-omi-local \
    EXPORT_DIR=/data/export
VOLUME /data
EXPOSE 8085 9099
ENTRYPOINT ["/app/entrypoint.sh"]
