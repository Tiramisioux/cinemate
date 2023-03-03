install:
	sudo cp cinepi-raw.service /etc/systemd/system/
	sudo cp manual_controls_simple_example.service /etc/systemd/system/
	sudo cp simple_gui.service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable cinepi-raw.service
	sudo systemctl enable manual_controls_simple_example.service
	sudo systemctl enable simple_gui.service
	sudo systemctl start cinepi-raw.service
	sudo systemctl start manual_controls_simple_example.service
	sudo systemctl start simple_gui.service

uninstall:
	sudo systemctl stop cinepi-raw.service
	sudo systemctl stop manual_controls_simple_example.service
	sudo systemctl stop simple_gui.service
	sudo systemctl disable cinepi-raw.service
	sudo systemctl disable manual_controls_simple_example.service
	sudo systemctl disable simple_gui.service
	sudo rm /etc/systemd/system/cinepi-raw.service
	sudo rm /etc/systemd/system/manual_controls_simple_example.service
	sudo rm /etc/systemd/system/simple_gui.service
	sudo systemctl daemon-reload
