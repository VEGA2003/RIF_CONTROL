import numpy as np
import pytest
import astropy
import astropy.units as u
from datetime import datetime
from telescope_control import Telescope

@pytest.fixture
def default_params():
    tele = Telescope("virtual")

    return tele

def test_pos_to_coord(default_params):
    tele = default_params
    dish = tele.dish_east
    observing_time = astropy.time.Time(datetime(2003, 2, 3, 13, 0))
    coord = astropy.coordinates.get_sun(observing_time)
    hadec = astropy.coordinates.HADec(location=tele.observing_location, obstime=observing_time)
    coordHADec = coord.transform_to(hadec)
    posDEC, posHA = dish.coord_to_pos(coordHADec, transform = False)
    coord_new = dish.pos_to_coord(posDEC, posHA)
    assert np.isclose(coordHADec.ha.to(u.radian), coord_new.ha.to(u.radian)) 
    assert np.isclose(coordHADec.dec.to(u.radian), coord_new.dec.to(u.radian)) 