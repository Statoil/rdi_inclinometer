from socket import gethostname

from enum import Enum


class ButtonType(Enum):
    short = 1
    long = 2

    def __str__(self):
        return self.name


class Binoculars:
    """
    Sews together all the sensors for the binocular
    """

    def __init__(self, button, gps, spatial, storage, say):
        self.storage = storage
        self.button = button
        self.say = say
        button.key_pressed = self.key_pressed

        if gps:
            self.gps = gps

        if spatial:
            self.spatial = spatial

    # noinspection PyTypeChecker
    # -- because IDEA interprets enum as int
    def key_pressed(self, length):
        print("Key pressed: {}".format(length))
        if length < 1.0:
            self.button_click(ButtonType.short)
        else:
            self.button_click(ButtonType.long)

    def button_click(self, button_type):
        """
        :type button_type: ButtonType

        Device will get a reading from the GPS, Accelerometer,
        Compass and Gyro,

        If user pressed the long button the device will reset
        the Gyro.
        """

        gps_fix = self.gps.get_fix()
        accelerometer_fix = self.spatial.get_accelerometer_fix()
        compass_fix = self.spatial.get_compass_fix()
        gyro_fix = self.spatial.get_gyro()
        gyro_momentary = self.spatial.get_gyro_momentary()
        roll_pitch_yaw = self.spatial.get_roll_pitch_yaw()
        sample_id = self.storage.store(host_name=gethostname(),
                                       gps_fix=gps_fix,
                                       gyro=gyro_fix,
                                       gyro_momentary=gyro_momentary,
                                       accelerometer_fix=accelerometer_fix,
                                       compass_fix=compass_fix,
                                       roll_pitch_yaw=roll_pitch_yaw,
                                       typ=str(button_type))

        if button_type == ButtonType.long:
            self.spatial.reset_gyro()
            # The user should hold the binoculars still for two seconds
            self.button.beep(0.1)
            self.say("horizon")
        else:
            self.button.beep(0.01)
        self.say(sample_id)

    def config_updated(self):
        self.spatial.update_from_config()
