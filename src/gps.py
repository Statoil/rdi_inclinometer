import datetime
from Phidgets.Devices.GPS import GPS


class GpsFix:
    """
    Contains info from a GPS position
    """
    def __init__(self, timestamp, latitude, longitude, altitude, heading, velocity):
        self.timestamp = timestamp
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude
        self.heading = heading
        self.velocity = velocity

    def __str__(self):
        return "t: {}, lat: {}, lon: {}, alt: {}, hdg: {}, vel: {}" \
            .format(self.timestamp, self.latitude, self.longitude, self.altitude, self.heading, self.velocity)

    def to_csv(self):
        return "{};{};{};{};{};{};".format(self.timestamp, self.latitude, self.longitude, self.altitude, self.heading, self.velocity)

    @staticmethod
    def read_from(gps):
        """
        Convenience method to read from Phidget GPS
        :type gps: GPS
        """
        if gps.getPositionFixStatus():
            t = gps.getTime()
            d = gps.getDate()
            timestamp=datetime.datetime(d.year, d.month, d.day, t.hour, t.min, t.sec, t.ms*1000)

            return GpsFix(timestamp=timestamp,
                      latitude=gps.getLatitude(),
                      longitude=gps.getLongitude(),
                      altitude=gps.getAltitude(),
                      heading=gps.getHeading(),
                      velocity=gps.getVelocity())
        else:
            nan = 0.0
            return GpsFix(datetime.datetime.now(), nan, nan, nan, nan, nan)

    @staticmethod
    def csv_headers():
        return "Gps_Time;Latitude;Longitude;Altitude;Heading;Velocity;"