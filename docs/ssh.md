# Connecting to the Pi with SSH

This guide shows how to log into the Raspberry Pi that runs Cinemate.

## Join the same network

Connect your computer and the Pi to the same network. If you are using the preinstalled image file, the system automatically starts a built-in hotspot: join the **CinePi** Wi‑Fi with password `11111111`.

You can change this behaviour later in the settings file.

## Find the Pi's address

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

## Connect

Use the hostname or IP address with SSH:
```bash
ssh pi@cinepi.local
# or
ssh pi@<ip-address>
```
When asked about the host key, type `yes`. Enter the default password `1` when prompted.

You will now see the `pi@cinepi` prompt, meaning you are logged in.

>If you are installing Cinemate manually, the hostname has not yet been set to cinepi. Then you will have to identify which ip address on the network is actually the Raspberry Pi and use that ip address.

## Next steps

From here you can run `cinemate` to start the interface or use `make` commands to manage the service. For security you should change the password with `passwd` after the first login.