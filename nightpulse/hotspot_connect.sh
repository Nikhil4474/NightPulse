#!/bin/sh
# Keeps the SK-AM62B joined to the phone hotspot, retrying forever.
# Run once:  sh hotspot_connect.sh        Install at boot:  sh hotspot_connect.sh install
# Credentials come from the environment, never from the repo:  HOTSPOT_SSID="MyPhone" HOTSPOT_PASS="secret" sh hotspot_connect.sh
SSID="${HOTSPOT_SSID:-}"; PASS="${HOTSPOT_PASS:-}"
[ -z "$SSID" ] || [ -z "$PASS" ] && { echo "Set HOTSPOT_SSID and HOTSPOT_PASS first."; exit 1; }
if [ "$1" = "install" ]; then
  P=$(readlink -f "$0")
  cat > /etc/systemd/system/hotspot.service <<UNIT
[Unit]
Description=Keep WiFi joined to phone hotspot
After=network.target
[Service]
Environment=HOTSPOT_SSID=$SSID
Environment=HOTSPOT_PASS=$PASS
ExecStart=/bin/sh $P
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload && systemctl enable --now hotspot.service && echo "installed; it now runs at every boot"; exit
fi
IF=$(ls /sys/class/net | grep -E '^(wlan|wlp|mlan)' | head -1)
[ -z "$IF" ] && { echo "NO WIFI INTERFACE on this board. Use Ethernet or a USB WiFi adapter."; exit 1; }
echo "WiFi interface: $IF"
while true; do
  if ip -4 addr show "$IF" 2>/dev/null | grep -q "inet " && iw dev "$IF" link 2>/dev/null | grep -q "SSID: $SSID"; then sleep 5; continue; fi
  echo "$(date +%T) joining $SSID ..."
  if command -v nmcli >/dev/null 2>&1; then
    nmcli radio wifi on 2>/dev/null; nmcli dev wifi rescan 2>/dev/null
    nmcli dev wifi connect "$SSID" password "$PASS" ifname "$IF" >/dev/null 2>&1
  else
    wpa_passphrase "$SSID" "$PASS" > /tmp/wpa_hotspot.conf
    pkill -f "wpa_supplicant.*$IF" 2>/dev/null; wpa_supplicant -B -i "$IF" -c /tmp/wpa_hotspot.conf
    udhcpc -i "$IF" -n -q 2>/dev/null || dhclient "$IF" 2>/dev/null
  fi
  sleep 5
  IPA=$(ip -4 addr show "$IF" | awk '/inet /{print $2}' | cut -d/ -f1)
  [ -n "$IPA" ] && echo "connected. Open http://$IPA:8000"
done
