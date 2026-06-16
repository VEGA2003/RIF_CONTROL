import numpy as np
import quaternion
import astropy
from astropy.time import Time
import astropy.units as u
import datetime
import matplotlib.pyplot as plt
from matplotlib import cm, colors
from mpl_toolkits.mplot3d import Axes3D



def pattern(coord):

    ra = coord.ra.to(u.radian).value
    dec= coord.dec.to(u.radian).value
    decc = np.pi/2  - dec
    x = np.sin(decc)*np.cos(ra)
    y = np.sin(decc)*np.sin(ra)
    z = np.cos(decc)
    real_vector = np.quaternion(0,x,y,z)
    vector = np.quaternion(0,1,0,0)

    h = np.array([-4,-3.5,-3 ,-2.5,-2, -1.5,-1, -0.5, 0, 0.5 ,1, 1.5,2,2.5, 3,3.5,4]) * np.pi/180
    v = np.array([-4,-3.5,-3 ,-2.5,-2, -1.5,-1, -0.5, 0, 0.5 ,1, 1.5,2,2.5, 3,3.5,4]) * np.pi/180
    coords = np.meshgrid(h, v)
    # coords[0][::2, :] *= -1
    rotation_array = np.zeros((len(h), len(v),3))
    coord_array = np.zeros((len(h), len(v), 2))
    v1 = np.array([1,0,0])
    v2 = np.array([x,y,z])
    v3 = (v1 + v2)/2
    v3 = v3/ np.sqrt(np.sum(v3**2))
    a = np.cross(v1, v3)
    b = np.dot(v1, v3)
    d = np.sqrt(np.sum(a**2)+ b**2)
    r3 = np.quaternion(b/d, a[0]/d, a[1]/d, a[2]/d)
    for i in range(len(coords[0])):
        for j in range(len(coords[0][0])):
            phi, theta = (coords[0][i, j], coords[1][i, j])
            r2 = np.quaternion(np.cos(theta/2), 0, np.sin(theta/2), 0) #dec
            r1 = np.quaternion(np.cos(phi/2), 0,0,np.sin(phi/2)) #ra
            r4 = np.quaternion(b, b*x,b*y,b*z)
            q = r1*vector*r2.conjugate()
            q = r2*q*r1.conjugate()
            q = r3*q*r3.conjugate()
            q = r4*q*r4.conjugate()
            rotation_array[i,j] = [q.x, q.y, q.z]
            coord_array[i, j] = [np.sign(q.y)*np.arccos(q.x/np.sqrt(q.x**2 + q.y**2)),np.pi/2 -np.arccos(q.z)]

    return rotation_array, coord_array

if __name__ == '__main__':
    # q1 = r3*vector*r3.conjugate()
    observing_time = Time(datetime.datetime.now())
    observing_location = astropy.coordinates.EarthLocation(lat='51.816694', lon='5.866694', height=20*u.m)
    sun_coords = astropy.coordinates.get_sun(observing_time)

    rotation_array, coord_array = pattern(sun_coords)
    # Plotting
    # Create a sphere
    r = 1
    pi = np.pi
    phi, theta = np.mgrid[0.0:pi:100j, 0.0:2.0*pi:100j]
    xx = r*np.sin(phi)*np.cos(theta)
    yy = r*np.sin(phi)*np.sin(theta)
    zz = r*np.cos(phi)

    #Set colours and render
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    # ax.plot_surface(
    #     xx, yy, zz,  rstride=1, cstride=1, color='c', alpha=0.3, linewidth=0)

    ax.scatter(rotation_array[:,:,0],rotation_array[:,:,1],rotation_array[:,:,2],color="k",s=20)
    ra = sun_coords.ra.to(u.radian).value
    dec= sun_coords.dec.to(u.radian).value
    decc = np.pi/2  - dec
    x = np.sin(decc)*np.cos(ra)
    y = np.sin(decc)*np.sin(ra)
    z = np.cos(decc)
    ax.scatter(x,y,z,color="b",s=20)
    ax.set_xlim([-1,1])
    ax.set_ylim([-1,1])
    ax.set_zlim([-1,1])
    ax.set_aspect("equal")
    plt.tight_layout()
    plt.show()