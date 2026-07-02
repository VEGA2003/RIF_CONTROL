import astropy as aa
import numpy as np
import datetime
import matplotlib.pyplot as plt
import matplotlib as mlb
from astropy.coordinates import Galactic, ICRS
from astropy.coordinates import SkyCoord
import astropy.coordinates as coords
import astropy.units as u
from astropy.time import Time
import csv

from astropy_healpix import HEALPix 
from astropy_healpix import healpy as hpp
import os

from tqdm import tqdm


def back_and_forth(points, save_list = True, output_path=None):
    current_dec = points.radian

    dec_list = []
    k = 0
    j = 0
    for i, point in enumerate(points):
        if point.radian != current_dec:
            j +=1
            current_dec = point.radian
            k = i
        if j %2==0:
            dec_list.append(point)
        else:
            dec_list.insert(k,point)
    
    if save_list:
        if output_path == None:
            output_path = datetime.date.today().strftime("%d%m%y_survey")
            
        if not os.path.exists(output_path):
            with open(output_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile, delimiter=',')
                writer.writerow(["RA", "DEC"])
                for point in points:
                    writer.writerow([point.ra, point.dec])   
    return dec_list

def import_survey(path):
    """
    import survey from csv

    Args:
        path: path of the csv file
    """
    pass

def get_spectrum(signal_0, signal_1):
    pass


def temp_conv(adc):
     """
     Convert ADC counts to temperatur in degrees Celsius
     """
     temp = 1.71234271e-02 * adc -1.91247311e+01
     return round(temp, 1)

def adc_conv(temp):
     """
     Convert degrees Celcius to ADC counts
     """
     return round((temp + 1.91247311e+01)/(1.71234271e-02))

def voltage_conv(dac, offset = 0x84E7):
    return round((dac - offset) * -0.000149, 1)

def dac_conv(v, offset = 0x84E7):
    return round((v / -0.000149) + offset)

def sky_survey(n, direction=1):
    nside = 2**n
    hp = HEALPix(nside=nside, order='ring', frame=ICRS())
    points = np.arange(hpp.nside2npix(nside))
    sky_coords = hp.healpix_to_skycoord(points)

    ra = coords.Angle(sky_coords.ra)
    ra = ra + 5.5 * u.hourangle
    ra = ra.wrap_at(180 * u.degree)
    dec = coords.Angle(sky_coords.dec)

    index = np.argwhere((ra.hourangle >= -5)&(ra.hourangle <5)&(dec.degree>0)&(dec.degree<=30))
    ra = direction * ra[index]
    dec = dec[index]
    current_dec = dec[0].radian

    index = []
    k = 0
    j = 0
    for i in range(len(ra.radian)):
        if dec.radian[i] != current_dec:
            if dec.deg[i] < 0:
                break
            j +=1
            current_dec = dec.radian[i]
            k = i
        if j %2==0:
            index.append(i)
        else:
            index.insert(k,i)

    ra = ra[index]
    dec = dec[index]
    return ra.radian, dec.radian