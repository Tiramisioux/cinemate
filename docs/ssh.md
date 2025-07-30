# Connecting to the Pi remotely with SSH

Connect your computer and the Pi to the same network.

!!! tip ""
    If you are using the preinstalled image file, the system automatically starts a built-in hotspot: join the **CinePi** Wi‑Fi with password `11111111`. You can change this behaviour later in the [settings file](settings-json.md).

Open a terminal (on Windows you can use PowerShell).

Try the hostname first:

```bash
ssh pi@cinepi.local
```

If this fails you can list devices on the network:

```bash
arp -a
```

Look for an entry labelled `cinepi` or note the new IP address that appears.


Use the hostname or IP address with SSH:
```bash
ssh pi@cinepi.local
# or
ssh pi@<ip-address>
```
When asked about the host key, type `yes`. Enter the default password `1` when prompted.

You will now see the `pi@cinepi` prompt, meaning you are logged in.

!!! note ""
    If you are installing Cinemate manually, the hostname has not yet been set to cinepi. Then you will have to identify which ip address on the network is actually the Raspberry Pi and use that ip address.

Tyoep `cinemate` anywhere in the cli to start the app. 

!!! tip ""
    If you are running Cinemate from the preinstalled image file, Cinemate is already running, as it autostarts on boot. [See here for how to manage the autostart-service](system-services.md).
