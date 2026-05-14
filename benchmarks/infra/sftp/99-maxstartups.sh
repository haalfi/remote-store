#!/bin/bash
# Raise MaxStartups so pytest-xdist workers probing port 2222 at session
# start don't saturate the OpenSSH default limit (10:30:100).
# Format: start:rate:full — random-drop begins at 100 (well above 20 workers),
# 30% rate between 100 and 200, drop all beyond 200.
echo "MaxStartups 100:30:200" >> /etc/ssh/sshd_config
