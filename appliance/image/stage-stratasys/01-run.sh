#!/bin/bash -e
# pi-gen stage: turn Raspberry Pi OS Lite into the Stratasys sCure appliance.
# Runs with ${ROOTFS_DIR} = the image root. Everything here is a *build-time*
# decision; nothing in this file runs on the customer's machine.

install -v -d "${ROOTFS_DIR}/opt/stratasys" "${ROOTFS_DIR}/usr/share/stratasys/keys" \
              "${ROOTFS_DIR}/usr/lib/stratasys" "${ROOTFS_DIR}/data" "${ROOTFS_DIR}/etc/chromium/policies/managed"

# ---- application (built outside: dist/ + server/ + io_controller/ of sCure-A) ----
cp -a "${STAGE_DIR}/app/." "${ROOTFS_DIR}/opt/stratasys/"
cp -a "${STAGE_DIR}/appliance-common/stratasys_appliance" "${ROOTFS_DIR}/opt/stratasys/"
cp -a "${STAGE_DIR}/security-service/security_service.py" "${ROOTFS_DIR}/opt/stratasys/"
cp "${STAGE_DIR}/VERSION" "${ROOTFS_DIR}/usr/share/stratasys/VERSION"
# public keys only: license-*.pub, image-*.pub, update CA. NEVER a .key file.
cp "${STAGE_DIR}/keys/"*.pub "${ROOTFS_DIR}/usr/share/stratasys/keys/"
cp "${STAGE_DIR}/keys/update-ca.pem" "${ROOTFS_DIR}/etc/rauc/ca.cert.pem"
if ls "${STAGE_DIR}/keys/"*.key >/dev/null 2>&1; then echo "REFUSING: private key in image keys/"; exit 1; fi

# ---- files: units, policies, boot config, initramfs hooks ----
cp -a "${STAGE_DIR}/files/." "${ROOTFS_DIR}/"

on_chroot << 'EOF'
set -e
# ---- users: one system user per service, nobody has a shell or password ----
for u in security hardware config logging; do
    useradd --system --no-create-home --shell /usr/sbin/nologin "$u" 2>/dev/null || true
done
usermod -aG i2c,gpio,spi,dialout,video hardware
usermod -aG tss security 2>/dev/null || true
usermod --shell /usr/sbin/nologin kiosk
passwd -l root
passwd -l kiosk
apt-get -y purge sudo 2>/dev/null || true

# ---- ownership / permissions ----
chown -R root:root /opt/stratasys
chmod -R o-rwx /opt/stratasys
chgrp -R hardware /opt/stratasys/server /opt/stratasys/io_controller
chmod 0750 /opt/stratasys/server /opt/stratasys/io_controller
chown security:security /opt/stratasys/security_service.py
mkdir -p /data/audit /data/identity /data/config
chown -R security:security /data/audit /data/identity
chmod 0700 /data/audit /data/identity
touch /data/provisioning.flag          # removed by the factory tool's last step

# ---- no way to the console ----
systemctl mask getty@tty1.service getty@tty2.service getty@tty3.service getty@tty4.service \
               getty@tty5.service getty@tty6.service autovt@.service serial-getty@ttyAMA0.service \
               serial-getty@ttyS0.service ctrl-alt-del.target emergency.service rescue.service \
               debug-shell.service
printf 'kernel.sysrq = 0\nkernel.dmesg_restrict = 1\nkernel.kptr_restrict = 2\n' > /etc/sysctl.d/90-stratasys.conf
printf '[Login]\nNAutoVTs=0\nReserveVT=0\nKillUserProcesses=yes\n' > /etc/systemd/logind.conf.d/stratasys.conf 2>/dev/null || \
  { mkdir -p /etc/systemd/logind.conf.d; printf '[Login]\nNAutoVTs=0\nReserveVT=0\nKillUserProcesses=yes\n' > /etc/systemd/logind.conf.d/stratasys.conf; }
mkdir -p /etc/systemd/system.conf.d
printf '[Manager]\nRuntimeWatchdogSec=15\nRebootWatchdogSec=2min\n' > /etc/systemd/system.conf.d/watchdog.conf

# ---- services ----
systemctl enable stratasys-security.service stratasys-hardware.service stratasys-kiosk.service \
                 usbguard.service rauc.service rauc-mark-good.service chrony.service
systemctl disable bluetooth.service triggerhappy.service 2>/dev/null || true
systemctl set-default multi-user.target

# ---- plymouth: Stratasys theme, no distro branding ----
plymouth-set-default-theme stratasys || true
rm -f /etc/motd /etc/issue /etc/issue.net
printf 'Stratasys sCure\n' > /etc/issue

# ---- no package manager on the appliance (immutable root) ----
apt-get -y clean
dpkg --purge --force-depends apt apt-utils 2>/dev/null || true
rm -rf /var/lib/apt/lists/* /var/cache/apt
EOF
