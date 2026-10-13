# Lean 4 image.
# Unpacks the pinned Lean release (lean, lake and the core library) for
# reproducible proof checking. No Mathlib: the proofs use Lean core only.
FROM debian:bookworm-slim AS fetch
RUN apt-get update \
 && apt-get install -y --no-install-recommends zstd \
 && rm -rf /var/lib/apt/lists/*

ARG LEAN_VERSION=4.34.1
# Pinned checksum of lean-4.34.1-linux.tar.zst (the digest GitHub publishes
# for the release asset), so local builds resolve to the same binary. Bump
# both with the list in scripts/lean_check.sh.
# Requires BuildKit >= 1.6.
ADD --checksum=sha256:47bf4bbd78f70c2e9670598ab7124d92b6efb7330ff33e5fbb4030f6fd72e4e4 \
    https://github.com/leanprover/lean4/releases/download/v${LEAN_VERSION}/lean-${LEAN_VERSION}-linux.tar.zst \
    /tmp/lean.tar.zst
RUN mkdir /opt/lean \
 && tar --zstd -xf /tmp/lean.tar.zst -C /opt/lean --strip-components=1

FROM debian:bookworm-slim
COPY --from=fetch /opt/lean /opt/lean
ENV PATH=/opt/lean/bin:$PATH
