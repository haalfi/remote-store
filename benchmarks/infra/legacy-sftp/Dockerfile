# Legacy SSH server forced to ssh-rsa (SHA-1) host-key + pubkey only.
# Used by `tests/e2e/test_sftp_legacy_recovery.py` to verify the recovery
# semantics of SFTPUtils.enable_ssh_rsa_compat() against a server that
# rejects modern host-key algorithms. See
# sdd/research/research-bk-198-paramiko-ssh-rsa-empirical.md for context.
FROM ubuntu:22.04

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /var/run/sshd \
 && useradd -m -s /bin/bash legacyuser \
 && echo 'legacyuser:legacypass' | chpasswd \
 && rm -f /etc/ssh/ssh_host_* \
 && ssh-keygen -t rsa -b 2048 -f /etc/ssh/ssh_host_rsa_key -N ''

RUN printf '%s\n' \
    'HostKey /etc/ssh/ssh_host_rsa_key' \
    'HostKeyAlgorithms ssh-rsa' \
    'PubkeyAcceptedAlgorithms ssh-rsa' \
    'CASignatureAlgorithms ssh-rsa' \
    'PasswordAuthentication yes' \
    'PermitRootLogin no' \
    > /etc/ssh/sshd_config.d/legacy.conf

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D", "-e"]
