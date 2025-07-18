# Recompiling cinepi-raw
Compiling cinepi-raw

For easy later rebuilding and installation of cinepi-raw you can create the file compile-raw.sh.

```shell
nano compile-raw.sh
```

Paste this into the file

```shell
sudo meson install -C build
```

Exit by pressing Ctrl+C

Make it exectutable:

```shell
sudo chmod +x compile-raw.sh
```

Now, from the same folder, to build and install cinepi-raw:

```shell
./compile-raw.sh
```