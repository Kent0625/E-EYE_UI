# Raspberry Pi Wi-Fi Hotspot Setup Guide (`192.168.4.1`)

The E-Eye device operates in remote rural environments without external internet connectivity. The Raspberry Pi broadcasts its own Wi-Fi Access Point (Hotspot), allowing the operator's smartphone, tablet, or laptop to connect directly and access the web UI at `http://192.168.4.1:5000`.

---

## Method 1: Raspberry Pi OS Bookworm (NetworkManager - Recommended)

Raspberry Pi OS Bookworm uses NetworkManager by default. Configuring a hotspot takes two commands:

### 1. Create Hotspot Connection
```bash
sudo nmcli connection add \
  type wifi \
  ifname wlan0 \
  con-name E-Eye-Hotspot \
  autoconnect yes \
  ssid "E-Eye-Refractor"

sudo nmcli connection modify E-Eye-Hotspot \
  802-11-wireless.mode ap \
  802-11-wireless.band bg \
  ipv4.method shared \
  ipv4.addresses 192.168.4.1/24 \
  wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk "eeyerefractor"
```
*(To create an open network without a password, omit `wifi-sec.key-mgmt` and `wifi-sec.psk`)*

### 2. Activate Hotspot
```bash
sudo nmcli connection up E-Eye-Hotspot
```

The Pi will automatically assign IP addresses in the `192.168.4.x` subnet to connecting client devices via NetworkManager's internal DHCP server.

---

## Method 2: Raspberry Pi OS Bullseye (Legacy `hostapd` + `dnsmasq`)

For legacy installations using `dhcpcd`:

### 1. Install Packages
```bash
sudo apt update
sudo apt install -y hostapd dnsmasq
sudo systemctl stop hostapd
sudo systemctl stop dnsmasq
```

### 2. Configure Static IP on `wlan0`
Edit `/etc/dhcpcd.conf`:
```conf
interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
```

### 3. Configure DHCP (`/etc/dnsmasq.conf`)
```conf
interface=wlan0
dhcp-range=192.168.4.10,192.168.4.100,255.255.255.0,24h
domain=eeye.local
address=/eeye.local/192.168.4.1
```

### 4. Configure Access Point (`/etc/hostapd/hostapd.conf`)
```conf
interface=wlan0
driver=nl80211
ssid=E-Eye-Refractor
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=eeyerefractor
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
```

Point `DAEMON_CONF` in `/etc/default/hostapd` to `/etc/hostapd/hostapd.conf`.

### 5. Enable and Start Services
```bash
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl start hostapd
sudo systemctl restart dnsmasq
sudo systemctl restart dhcpcd
```

---

## Verification & Connecting

1. On the operator device (phone/tablet/laptop), connect to Wi-Fi SSID **`E-Eye-Refractor`** using password `eeyerefractor`.
2. Verify the client device receives an IP like `192.168.4.15`.
3. Open a browser and navigate to:
   ```
   http://192.168.4.1:5000
   ```
4. Optional Port 80 Redirect (to omit `:5000` in URL):
   ```bash
   sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 5000
   sudo iptables-save | sudo tee /etc/iptables.ipv4.nat
   ```
