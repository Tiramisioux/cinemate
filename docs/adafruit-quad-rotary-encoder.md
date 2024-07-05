### Quad ENCODER I2C Peripheral and Its Application in CineMate

#### Overview of the Adafruit I2C QT Rotary Encoder Breakout

The Adafruit I2C QT Rotary Encoder Breakout, part number 5752, is a versatile and compact module designed to interface rotary encoders with microcontroller projects via the I2C bus. This module includes four rotary encoders and associated push buttons, all managed through the Seesaw firmware, which simplifies the integration process by offloading the handling of complex tasks to the breakout board itself. 

**Key Features:**
- **I2C Interface**: Uses the I2C bus for communication, minimizing the number of GPIO pins required.
- **Seesaw Firmware**: Handles the intricacies of rotary encoder inputs and push button states.
- **Integrated NeoPixel LEDs**: Provides visual feedback for each rotary encoder position.
- **Compact Design**: Suitable for projects with limited space.

For more details, visit the [product page on Adafruit](https://www.adafruit.com/product/5752).

#### Application in CineMate

CineMate utilizes the Adafruit I2C QT Rotary Encoder Breakout to enhance user interaction and control over various camera settings. This module, referred to as the "Quad Rotary Encoder" within the CineMate system, is integrated to provide precise adjustments for settings such as ISO, shutter angle, and frame rate.

#### Integration in the CineMate System

The `QuadRotaryEncoder` class within the `gpio_input.py` module is responsible for interfacing with the Adafruit I2C QT Rotary Encoder Breakout. Here’s a breakdown of its functionality:

**Initialization and Configuration:**
- **I2C Setup**: The class initializes the I2C bus and configures the rotary encoders and push buttons using the Seesaw firmware.
- **Settings Mapping**: A dictionary maps each encoder to specific camera settings, enabling tailored control for each rotary encoder.
- **Button and LED Configuration**: Sets up the push buttons and NeoPixel LEDs for each encoder, providing visual and interactive feedback.

**Runtime Operation:**
- **Position Tracking**: Continuously monitors the position of each rotary encoder to detect changes.
- **Setting Adjustments**: Updates the corresponding camera settings based on the encoder movements. For instance, turning an encoder clockwise might increase the ISO, while counterclockwise movement decreases it.
- **Button Press Handling**: Manages the state of the push buttons, triggering specific actions when pressed or held.

**Example Usage:**

1. **Initialization**:
   The `QuadRotaryEncoder` is initialized with references to the `cinepi_controller`, settings, and a list of `smart_buttons`. This setup ensures that all necessary components are properly configured.

   ```python
   self.quad_rotary_encoder = QuadRotaryEncoder(
       self.cinepi_controller,
       quad_rotary_settings,
       self,
       self.smart_buttons_list  # Pass the list of smart buttons
   )
   ```

2. **Setting Adjustments**:
   The `update_setting` method adjusts the camera settings based on the rotary encoder movements. It dynamically calls the increment or decrement functions defined in the `cinepi_controller`.

   ```python
   def update_setting(self, encoder_index, change):
       setting_name = self.settings_mapping[str(encoder_index)].get('setting_name')
       if setting_name is not None:
           inc_func_name = f"inc_{setting_name}"
           dec_func_name = f"dec_{setting_name}"
           if hasattr(self.cinepi_controller, inc_func_name) and hasattr(self.cinepi_controller, dec_func_name):
               if change > 0:
                   getattr(self.cinepi_controller, inc_func_name)()
               elif change < 0:
                   getattr(self.cinepi_controller, dec_func_name)()
   ```

3. **Button Handling**:
   The `handle_button_press` and `handle_button_release` methods manage the state of the push buttons, triggering actions defined in the settings.

   ```python
   def handle_button_press(self, encoder_index):
       button_pin = self.settings_mapping[str(encoder_index)].get('gpio_pin')
       if button_pin is not None:
           smart_button = self.component_initializer.get_smart_button_by_pin(button_pin)
           if smart_button is not None:
               smart_button.on_press()
   ```

### Conclusion

The integration of the Adafruit I2C QT Rotary Encoder Breakout in CineMate significantly enhances the system's usability by providing precise, intuitive controls for key camera settings. This implementation leverages the strengths of the Seesaw firmware and the I2C interface to deliver a responsive and flexible user experience, allowing filmmakers to make quick adjustments on the fly.

### Configuring the Quad Rotary Encoder in CineMate

The `settings.json` file of the CineMate project contains the configuration for various components, including the quad rotary encoder. Here’s a guide on how to configure the quad rotary encoder for your CineMate setup.

#### Quad Rotary Encoder Configuration

In the `settings.json` file, the quad rotary encoder is configured under the `quad_rotary_encoders` key. Each encoder can be mapped to control a specific camera setting, such as ISO, shutter angle, or frame rate.

Here is the relevant section from the `settings.json` file:

```json
"quad_rotary_encoders": {
    "0": {
        "setting_name": "iso",
        "gpio_pin": 26
    },
    "1": {
        "setting_name": "shutter_a",
        "gpio_pin": 24
    },
    "2": {
        "setting_name": "shutter_a",
        "gpio_pin": 24
    },
    "3": {
        "setting_name": "fps",
        "gpio_pin": 16
    }
}
```

#### Configuration Details

1. **Setting Name**: This indicates which camera setting the encoder controls.
2. **GPIO Pin**: This specifies the GPIO pin associated with the encoder button. This can be used for additional functionalities like pressing the encoder button to lock a setting.

#### Steps to Configure

1. **Identify the Encoder Index**: The quad rotary encoder has four encoders, indexed from `0` to `3`.

2. **Assign Settings**: For each encoder, specify the `setting_name` that you want the encoder to control. Possible values are `iso`, `shutter_a`, and `fps`.

3. **Specify GPIO Pins**: Optionally, assign a `gpio_pin` to each encoder if you want to use the push button on the encoder for additional actions.

#### Example Configuration

Here’s an example of how you might configure the quad rotary encoder for different settings:

```json
"quad_rotary_encoders": {
    "0": {
        "setting_name": "iso",
        "gpio_pin": 26
    },
    "1": {
        "setting_name": "shutter_a",
        "gpio_pin": 24
    },
    "2": {
        "setting_name": "shutter_a",
        "gpio_pin": 24
    },
    "3": {
        "setting_name": "fps",
        "gpio_pin": 16
    }
}
```

In this configuration:
- Encoder `0` adjusts the ISO setting and uses GPIO pin `26` for its push button.
- Encoders `1` and `2` both adjust the shutter angle and use GPIO pin `24`.
- Encoder `3` adjusts the frame rate (fps) and uses GPIO pin `16`.

### Applying Changes

Once you have updated the `settings.json` file with your desired configuration, restart the CineMate application to apply the changes. The quad rotary encoders will now control the specified camera settings according to your configuration.

### Conclusion

By configuring the quad rotary encoder in the `settings.json` file, you can customize the control scheme of your CineMate setup to suit your specific needs. This setup allows for precise adjustments of key camera settings, enhancing the overall usability and functionality of your Raspberry Pi-based cinema camera.