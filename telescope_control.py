from astropy.coordinates import EarthLocation,SkyCoord
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import AltAz
from datetime import datetime
from system_config import ARS2108System


class Telescope():
    
    def __init__(self):    
        # default observing location is the Huygens building :)
        self.observing_location = EarthLocation(lat='51.816694', lon='5.866694', height=20*u.m)  
        self.conversion_factor_alt = 0.001
        self.alt_offset = 0
        self.az_offset = 0
        self.conversion_factor_az = 0.001
        self.revolutions_to_increments = 6553600
        self.system = ARS2108System()
        
    def coord_to_pos(self, ra, dec, observing_time=None):
        if observing_time == None:
            observing_time = Time(datetime.now())
        
        aa = AltAz(location=self.observing_location, obstime=observing_time)
        coord = SkyCoord(ra, dec)
        coordAltAz = coord.transform_to(aa)
        
        posalt = int(((coordAltAz.alt.value - self.alt_offset)*self.conversion_factor_alt)*self.revolutions_to_increments)
        posaz = int(((coordAltAz.az.value - self.az_offset)*self.conversion_factor_az)*self.revolutions_to_increments)
        
        return posalt, posaz
        
    def move_to(self, ra: str , dec: str):
        posalt, posaz = self.coord_to_pos(ra, dec)
        self.system.set_position_sdo(posalt)
    
        


