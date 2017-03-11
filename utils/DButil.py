import numpy as np
import os
import Tkinter
import tkFileDialog

__author__ = ["Sijie Yu"]
__email__ = "sijie.yu@njit.edu"


# def mkunidir(dirlist, isdir=True):
#     '''
#     get the list of all unique directories from the filelist, make these directories
#     :param dirlist:
#     :param isdir: if dirlist is a list of directories.
#                 if not, dirlist is a list of full path of files,
#                 the base name will be removed from the paths.
#     :return:
#     '''
#     import os
#     if not isdir:
#         dirlist = [os.path.dirname(ff) for ff in dirlist]
#     dirs = list(set(dirlist))
#     for ll in dirs:
#         if not os.path.exists(ll):
#             os.makedirs(ll)


def getsdodir(filename, unique=True):
    '''
    return a list of the data path relative to the SDO_dir
    :param filename:
    :return:
    '''
    if type(filename) == str:
        filename = [filename]
    dirlist = []
    timstrs = []
    if unique:
        for ll in filename:
            timstr = os.path.basename(ll).split('.')[2].split('T')[0]
            ymd = timstr.replace('-', '/')
            dirlist.append('/{}/_{}'.format(ymd, timstr))
        dirlist = list(set(dirlist))
        for ll, dd in enumerate(dirlist):
            dirlist[ll], timstr = dd.split('_')
            timstrs.append(timstr)
    else:
        for ll in filename:
            timstr = os.path.basename(ll).split('.')[2].split('T')[0]
            ymd = timstr.replace('-', '/')
            dirlist.append('/{}/'.format(ymd))
            timstrs.append(timstr)
    return {'dir': dirlist, 'timstr': timstrs}


def FileNotInList(file2chk, filelist):
    '''
    return the index of files not in the list
    :param file2chk: files to be check
    :param filelist: the list
    :return:
    '''
    idxs = []
    if len(file2chk) > 0:
        filelist = [os.path.basename(ll) for ll in filelist]
        for idx, items in enumerate(file2chk):
            if items not in filelist:
                idxs.append(idx)
    return idxs


def getfreeport():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('localhost', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def normalize_aiamap(smap):
    '''
    do expisure normalization of an aia map
    :param aia map made from sunpy.map:
    :return: normalised aia map
    '''
    try:
        if smap.observatory == 'SDO' and smap.instrument[0:3] == 'AIA':
            data = smap.data
            data[~np.isnan(data)] = data[~np.isnan(
                data)] / smap.exposure_time.value
            smap.data = data
            smap.meta['exptime'] = 1.0
            return smap
        else:
            raise ValueError('input sunpy map is not from aia.')
    except:
        raise ValueError('check your input map. There are some errors in it.')


def sdo_aia_scale_dict(wavelength=None):
    '''
    rescale the aia image
    :param image: normalised aia image data
    :param wavelength:
    :return: byte scaled image data
    '''
    if wavelength == '94':
        return {'low': 3, 'high': 150}
    elif wavelength == '131':
        return {'low': 3, 'high': 200}
    elif wavelength == '171':
        return {'low': 20, 'high': 5000}


def sdo_aia_scale(image=None, wavelength=None):
    '''
    rescale the aia image
    :param image: normalised aia image data
    :param wavelength:
    :return: byte scaled image data
    '''
    from scipy.misc import bytescale
    clrange = sdo_aia_scale_dict(wavelength)
    image[image > clrange['high']] = clrange['high']
    image[image < clrange['low']] = clrange['low']
    image = np.log10(image)
    return bytescale(image)


def insertchar(source_str, insert_str, pos):
    return source_str[:pos] + insert_str + source_str[pos:]


# def get_trange_files(trange):
#     '''
#     Given a timerange, this routine will take all relevant SDO files from that time range,
#     put them in a list, and return that list.
#     :param trange: two elements list of timestamps in Julian days
#     :return:
#     '''


def readsdofile(datadir=None, wavelength=None, jdtime=None, isexists=False, timtol=1):
    '''
    read sdo file from local database
    :param datadir:
    :param wavelength:
    :param jdtime: the timestamp or timerange in Julian days. if is timerange, return a list of files in the timerange
    :param isexists: check if file exist. if files exist, return file name
    :param timtol: time difference tolerance in days for considering data as the same timestamp
    :return:
    '''
    import glob
    import os
    from astropy.time import Time
    import sunpy.map
    from datetime import date, timedelta as td

    if timtol < 12. / 3600 / 24:
        timtol = 12. / 3600 / 24
    if isinstance(jdtime, list) or isinstance(jdtime, tuple) or type(jdtime) == np.ndarray:
        if len(jdtime) != 2:
            raise ValueError('jdtime must be a number or a two elements array/list/tuple')
        else:
            if jdtime[1] < jdtime[0]:
                raise ValueError('start time must be occur earlier than end time!')
            else:
                sdofitspath = []
                jdtimestr = [Time(ll, format='jd').iso for ll in jdtime]
                ymd = [ll.split(' ')[0].split('-') for ll in jdtimestr]
                d1 = date(int(ymd[0][0]), int(ymd[0][1]), int(ymd[0][2]))
                d2 = date(int(ymd[1][0]), int(ymd[1][1]), int(ymd[1][2]))
                delta = d2 - d1
                for i in xrange(delta.days + 1):
                    ymd = d1 + td(days=i)
                    sdofitspathtmp = glob.glob(
                        datadir + '/{:04d}/{:02d}/{:02d}/aia.lev1_*Z.{}.image_lev1.fits'.format(ymd.year, ymd.month,
                                                                                                ymd.day, wavelength))
                    if len(sdofitspathtmp) > 0:
                        sdofitspath = sdofitspath + sdofitspathtmp
                if len(sdofitspath) == 0:
                    raise ValueError(
                        'No SDO file found under {} at the time range of {} to {}. Download the data with EvtBrowser first.'.format(
                            datadir, jdtimestr[0], jdtimestr[1]))
                sdofits = [os.path.basename(ll) for ll in sdofitspath]
                sdotimeline = Time(
                    [insertchar(insertchar(ll.split('.')[2].replace('T', ' ').replace('Z', ''), ':', -4), ':', -2)
                     for
                     ll in sdofits], format='iso', scale='utc')
                sdofile = list(np.array(sdofitspath)[
                                   np.where(np.logical_and(jdtime[0] < sdotimeline.jd, sdotimeline.jd < jdtime[1]))[0]])
                return sdofile
    else:
        jdtimstr = Time(jdtime, format='jd').iso
        ymd = jdtimstr.split(' ')[0].split('-')
        sdofitspath = glob.glob(
            datadir + '/{}/{}/{}/aia.lev1_*Z.{}.image_lev1.fits'.format(ymd[0], ymd[1], ymd[2], wavelength))
        if len(sdofitspath) == 0:
            raise ValueError('No SDO file found under {}.'.format(datadir))
        sdofits = [os.path.basename(ll) for ll in sdofitspath]
        sdotimeline = Time(
            [insertchar(insertchar(ll.split('.')[2].replace('T', ' ').replace('Z', ''), ':', -4), ':', -2)
             for
             ll in sdofits], format='iso', scale='utc')
        if timtol < np.min(np.abs(sdotimeline.jd - jdtime)):
            raise ValueError('No SDO file found at the select timestamp. Download the data with EvtBrowser first.')
        idxaia = np.argmin(np.abs(sdotimeline.jd - jdtime))
        sdofile = sdofitspath[idxaia]
        if isexists:
            return sdofile
        else:
            try:
                sdomap = sunpy.map.Map(sdofile)
                return sdomap
            except:
                raise ValueError('File not found or invalid input')


def findDist(x, y):
    dx = np.diff(x)
    dy = np.diff(y)
    dist = np.hypot(dx, dy)
    return np.insert(dist, 0, 0.0)


def paramspline(x, y, length, s=0):
    from scipy.interpolate import splev, splprep
    tck, u = splprep([x, y], s=s)
    unew = np.linspace(0, u[-1], length)
    out = splev(unew, tck)
    xs, ys = out[0], out[1]
    grads = get_curve_grad(xs, ys)
    return {'xs': xs, 'ys': ys, 'grads': grads['grad'], 'posangs': grads['posang']}


def polyfit(x, y, length, deg):
    xs = np.linspace(x.min(), x.max(), length)
    z = np.polyfit(x=x, y=y, deg=deg)
    p = np.poly1d(z)
    ys = p(xs)
    grads = get_curve_grad(xs, ys)
    return {'xs': xs, 'ys': ys, 'grads': grads['grad'], 'posangs': grads['posang']}


def spline(x, y, length, s=0):
    from scipy.interpolate import splev, splrep
    xs = np.linspace(x.min(), x.max(), length)
    tck = splrep(x, y, s=s)
    ys = splev(xs, tck)
    grads = get_curve_grad(xs, ys)
    return {'xs': xs, 'ys': ys, 'grads': grads['grad'], 'posangs': grads['posang']}


def get_curve_grad(x, y):
    '''
    get the grad of at data point
    :param x:
    :param y:
    :return: grad,posang
    '''
    deltay = np.roll(y, -1) - np.roll(y, 1)
    deltay[0] = y[1] - y[0]
    deltay[-1] = y[-1] - y[-2]
    deltax = np.roll(x, -1) - np.roll(x, 1)
    deltax[0] = x[1] - x[0]
    deltax[-1] = x[-1] - x[-2]
    grad = deltay / deltax
    posang = np.arctan2(deltay, deltax)
    return {'grad': grad, 'posang': posang}


def improfile(z, xi, yi, interp='cubic'):
    '''
    Pixel-value cross-section along line segment in an image
    :param z: an image array
    :param xi and yi: equal-length vectors specifying the pixel coordinates of the endpoints of the line segment
    :param interp: interpolation type to sampling, 'nearest' or 'cubic'
    :return: the intensity values of pixels along the line
    '''
    import scipy.ndimage
    imgshape = z.shape
    if len(xi) != len(yi):
        raise ValueError('xi and yi must be equal-length!')
    if len(xi) < 2:
        raise ValueError('xi or yi must contain at least two elements!')
    for idx, ll in enumerate(xi):
        if not 0 < ll < imgshape[1]:
            raise ValueError('xi out of range!')
        if not 0 < yi[idx] < imgshape[0]:
            raise ValueError('yi out of range!')
            # xx, yy = np.meshgrid(x, y)
    if len(xi) == 2:
        length = np.hypot(np.diff(xi), np.diff(yi))[0]
        x, y = np.linspace(xi[0], xi[1], length), np.linspace(yi[0], yi[1], length)
    else:
        x, y = xi, yi
    if interp == 'cubic':
        zi = scipy.ndimage.map_coordinates(z, np.vstack((x, y)))
    else:
        zi = z[np.floor(y).astype(np.int), np.floor(x).astype(np.int)]

    return zi


def canvaspix_to_data(smap, x, y):
    import astropy.units as u
    '''
    Convert canvas pixel coordinates in MkPlot to data (world) coordinates by using
    `~astropy.wcs.WCS.wcs_pix2world`.

    :param smap: sunpy map
    :param x: canvas Pixel coordinates of the CTYPE1 axis. (Normally solar-x)
    :param y: canvas Pixel coordinates of the CTYPE2 axis. (Normally solar-y)
    :return: world coordinates
    '''
    xynew = smap.pixel_to_data(x * u.pix, y * u.pix)
    xnew = xynew[0].value
    ynew = xynew[1].value
    return [xnew, ynew]


def data_to_mappixel(smap, x, y):
    import astropy.units as u
    '''
    Convert data (world) coordinates in MkPlot to pixel coordinates in smap by using
    `~astropy.wcs.WCS.wcs_pix2world`.

    :param smap: sunpy map
    :param x: Data coordinates of the CTYPE1 axis. (Normally solar-x)
    :param y: Data coordinates of the CTYPE2 axis. (Normally solar-y)
    :return: pixel coordinates
    '''
    xynew = smap.data_to_pixel(x * u.arcsec, y * u.arcsec)
    xnew = xynew[0].value
    ynew = xynew[1].value
    return [xnew, ynew]


def polsfromfitsheader(header):
    '''
    get polarisation information from fits header
    :param header: fits header
    :return pols: polarisation stokes
    '''
    try:
        stokeslist = ['{}'.format(int(ll)) for ll in
                      (header["CRVAL4"] + np.arange(header["NAXIS4"]) * header["CDELT4"])]
        stokesdict = {'1': 'I', '2': 'Q', '3': 'U', '4': 'V', '-1': 'RR', '-2': 'LL', '-3': 'RL', '-4': 'LR',
                      '-5': 'XX', '-6': 'YY', '-7': 'XY', '-8': 'YX'}
        pols = map(lambda x: stokesdict[x], stokeslist)
    except:
        print("error in fits header!")
    return pols


def freqsfromfitsheader(header):
    '''
    get frequency in GHz from fits header
    :param header: fits header
    :return pols: polarisation stokes
    '''
    try:
        freqs = ['{:.3f}'.format(ll / 1e9) for ll in
                 (header["CRVAL3"] + np.arange(header["NAXIS3"]) * header["CDELT3"])]
        return freqs
    except:
        print("error in fits header!")
        raise ValueError


def transfitdict2DF(datain, gaussfit=True):
    '''
    convert the results from pimfit or pmaxfit tasks to pandas DataFrame structure.
    :param datain: The component list from pimfit or pmaxfit tasks
    :param gaussfit: True if the results is from pimfit, otherwise False.
    :return: the pandas DataFrame structure.
    '''
    import pandas as pd

    ra2arcsec = 180. * 3600. / np.pi
    dspecDF0 = pd.DataFrame()
    for ll in datain['timestamps']:
        tidx = datain['timestamps'].index(ll)
        if datain['succeeded'][tidx]:
            pols = datain['outputs'][tidx].keys()
            dspecDFlist = []
            dspecDF = pd.DataFrame()
            for ppit in pols:
                dspecDFtmp = pd.DataFrame()
                shape_latitude = []
                shape_longitude = []
                shape_latitude_err = []
                shape_longitude_err = []
                shape_majoraxis = []
                shape_minoraxis = []
                shape_positionangle = []
                peak = []
                beam_major = []
                beam_minor = []
                beam_positionangle = []
                freqstrs = []
                fits_local = []
                for comp in datain['outputs'][tidx][ppit]['results'].keys():
                    if comp.startswith('component'):
                        if gaussfit:
                            majoraxis = datain['outputs'][tidx][ppit]['results'][comp]['shape']['majoraxis']['value']
                            minoraxis = datain['outputs'][tidx][ppit]['results'][comp]['shape']['minoraxis']['value']
                            positionangle = datain['outputs'][tidx][ppit]['results'][comp]['shape']['positionangle'][
                                'value']
                            bmajor = datain['outputs'][tidx][ppit]['results'][comp]['beam']['beamarcsec']['major'][
                                'value']
                            bminor = datain['outputs'][tidx][ppit]['results'][comp]['beam']['beamarcsec']['minor'][
                                'value']
                            bpositionangle = \
                                datain['outputs'][tidx][ppit]['results'][comp]['beam']['beamarcsec']['positionangle'][
                                    'value']
                            shape_majoraxis.append(majoraxis)
                            shape_minoraxis.append(minoraxis)
                            shape_positionangle.append(positionangle)
                            beam_major.append(bmajor)
                            beam_minor.append(bminor)
                            beam_positionangle.append(bpositionangle)
                            fluxpeak = datain['outputs'][tidx][ppit]['results'][comp]['peak']['value']
                        else:
                            fluxpeak = datain['outputs'][tidx][ppit]['results'][comp]['flux']['value'][0]
                        longitude = datain['outputs'][tidx][ppit]['results'][comp]['shape']['direction']['m0'][
                                        'value'] * ra2arcsec
                        latitude = datain['outputs'][tidx][ppit]['results'][comp]['shape']['direction']['m1'][
                                       'value'] * ra2arcsec
                        longitude_err = \
                            datain['outputs'][tidx][ppit]['results'][comp]['shape']['direction']['error']['longitude'][
                                'value']
                        latitude_err = \
                            datain['outputs'][tidx][ppit]['results'][comp]['shape']['direction']['error']['latitude'][
                                'value']
                        shape_longitude.append(longitude)
                        shape_latitude.append(latitude)
                        shape_longitude_err.append(longitude_err)
                        shape_latitude_err.append(latitude_err)
                        peak.append(fluxpeak)
                        freqstrs.append('{:.3f}'.format(
                            datain['outputs'][tidx][ppit]['results'][comp]['spectrum']['frequency']['m0']['value']))
                        fits_local.append(datain['imagenames'][tidx].split('/')[-1])
                if gaussfit:
                    dspecDFtmp['shape_latitude{}'.format(ppit)] = pd.Series(shape_latitude)
                    dspecDFtmp['shape_longitude{}'.format(ppit)] = pd.Series(shape_longitude)
                    dspecDFtmp['shape_latitude_err{}'.format(ppit)] = pd.Series(shape_latitude_err)
                    dspecDFtmp['shape_longitude_err{}'.format(ppit)] = pd.Series(shape_longitude_err)
                    dspecDFtmp['peak{}'.format(ppit)] = pd.Series(peak)
                    dspecDFtmp['shape_majoraxis{}'.format(ppit)] = pd.Series(shape_majoraxis)
                    dspecDFtmp['shape_minoraxis{}'.format(ppit)] = pd.Series(shape_minoraxis)
                    dspecDFtmp['shape_positionangle{}'.format(ppit)] = pd.Series(shape_positionangle)
                    dspecDFtmp['beam_major{}'.format(ppit)] = pd.Series(beam_major)
                    dspecDFtmp['beam_minor{}'.format(ppit)] = pd.Series(beam_minor)
                    dspecDFtmp['beam_positionangle{}'.format(ppit)] = pd.Series(beam_positionangle)
                else:
                    dspecDFtmp['shape_latitude{}'.format(ppit)] = pd.Series(shape_latitude)
                    dspecDFtmp['shape_longitude{}'.format(ppit)] = pd.Series(shape_longitude)
                    dspecDFtmp['shape_latitude_err{}'.format(ppit)] = pd.Series(shape_latitude_err)
                    dspecDFtmp['shape_longitude_err{}'.format(ppit)] = pd.Series(shape_longitude_err)
                    dspecDFtmp['peak{}'.format(ppit)] = pd.Series(peak)
                dspecDFtmp['freqstr'.format(ppit)] = pd.Series(freqstrs)
                dspecDFtmp['fits_local'.format(ppit)] = pd.Series(fits_local)
                dspecDFlist.append(dspecDFtmp)
            for DFidx, DFit in enumerate(dspecDFlist):
                if DFidx == 0:
                    dspecDF = dspecDFlist[0]
                else:
                    dspecDF = pd.merge(dspecDF.copy(), DFit, how='outer', on=['freqstr', 'fits_local'])
            dspecDF0 = dspecDF0.append(dspecDF, ignore_index=True)

    return dspecDF0


def getcolctinDF(dspecDF, col):
    '''
    return the count of how many times of the element starts with col occurs in columns of dspecDF
    :param dspecDF:
    :param col: the start string
    :return: the count and items
    '''
    itemset1 = col
    itemset2 = dspecDF.columns.tolist()
    items = []
    for ll in itemset2:
        if ll.startswith(itemset1):
            items.append(ll)
    itemct = [ll.startswith(itemset1) for ll in itemset2].count(True)
    columns = items
    return [itemct, columns]


def dspecDFfilter(dspecDF, pol):
    '''
    filter the unselect polarisation from dspecDF
    :param dspecDF: the original dspecDF
    :param pol: selected polarisation, dtype = string
    :return: the output dspecDF
    '''
    colnlistcom = ['shape_latitude', 'shape_longitude', 'peak', 'shape_latitude_err', 'shape_longitude_err']
    colnlistgaus = ['shape_majoraxis', 'shape_minoraxis', 'shape_positionangle', 'beam_major', 'beam_minor',
                    'beam_positionangle']
    ## above are the columns to filter
    colnlistess = dspecDF.columns.tolist()
    if getcolctinDF(dspecDF, 'peak')[0] > 1:
        for ll in colnlistcom + colnlistgaus:
            colinfo = getcolctinDF(dspecDF, ll)
            if colinfo[0] > 0:
                for cc in colinfo[1]:
                    if cc in colnlistess:
                        colnlistess.remove(cc)
        dspecDF1 = dspecDF.copy()[colnlistess]
        for ll in colnlistcom:
            dspecDF1[ll] = dspecDF.copy()[ll + pol]
        if getcolctinDF(dspecDF, 'shape_majoraxis')[0] > 0:
            for ll in colnlistgaus:
                dspecDF1[ll] = dspecDF.copy()[ll + pol]
        return dspecDF1
    else:
        return dspecDF


def get_contour_data(X, Y, Z):
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm
    from bokeh.models import (ColumnDataSource)
    cs = plt.contour(X, Y, Z, levels=(np.arange(5, 10, 2) / 10.0 * np.nanmax(Z)).tolist(), cmap=cm.Greys_r)
    xs = []
    ys = []
    xt = []
    yt = []
    col = []
    text = []
    isolevelid = 0
    for isolevel in cs.collections:
        # isocol = isolevel.get_color()[0]
        # thecol = 3 * [None]
        theiso = '{:.0f}%'.format(cs.get_array()[isolevelid] / Z.max() * 100)
        isolevelid += 1
        # for i in xrange(3):
        # thecol[i] = int(255 * isocol[i])
        thecol = '#%02x%02x%02x' % (220, 220, 220)
        # thecol = '#03FFF9'

        for path in isolevel.get_paths():
            v = path.vertices
            x = v[:, 0]
            y = v[:, 1]
            xs.append(x.tolist())
            ys.append(y.tolist())
            xt.append(x[len(x) / 2])
            yt.append(y[len(y) / 2])
            text.append(theiso)
            col.append(thecol)

    source = ColumnDataSource(data={'xs': xs, 'ys': ys, 'line_color': col, 'xt': xt, 'yt': yt, 'text': text})
    return source


def twoD_Gaussian((x, y), amplitude, xo, yo, sigma_x, sigma_y, theta, offset):
    xo = float(xo)
    yo = float(yo)
    a = (np.cos(theta) ** 2) / (2 * sigma_x ** 2) + (np.sin(theta) ** 2) / (2 * sigma_y ** 2)
    b = -(np.sin(2 * theta)) / (4 * sigma_x ** 2) + (np.sin(2 * theta)) / (4 * sigma_y ** 2)
    c = (np.sin(theta) ** 2) / (2 * sigma_x ** 2) + (np.cos(theta) ** 2) / (2 * sigma_y ** 2)
    g = offset + amplitude * np.exp(- (a * ((x - xo) ** 2) + 2 * b * (x - xo) * (y - yo) + c * ((y - yo) ** 2)))
    return g.ravel()


def c_correlate(a, v):
    a = (a - np.mean(a)) / (np.std(a) * len(a))
    v = (v - np.mean(v)) / np.std(v)
    return np.correlate(a, v, mode='same')


def XCorrMap(z, x, y, doxscale=True):
    '''
    get the cross correlation map along y axis
    :param z: data
    :param x: x axis
    :param y: y axis
    :return:
    '''
    from scipy.interpolate import splev, splrep
    if doxscale:
        xfit = np.linspace(x[0], x[-1], 10 * len(x) + 1)
        zfit = np.zeros((len(y), len(xfit)))
        for yidx1, yq in enumerate(y):
            xx = x
            yy = z[yidx1, :]
            s = len(yy)  # (len(yy) - np.sqrt(2 * len(yy)))*2
            tck = splrep(xx, yy, s=s)
            ys = splev(xfit, tck)
            zfit[yidx1, :] = ys
    else:
        xfit = x
        zfit = z
    ny, nxfit = zfit.shape
    ccpeak = np.empty((ny - 1, ny - 1))
    ccpeak[:] = np.nan
    ccmax = ccpeak.copy()
    ya = ccpeak.copy()
    yv = ccpeak.copy()
    yidxa = ccpeak.copy()
    yidxv = ccpeak.copy()
    for idx1 in xrange(1, ny):
        for idx2 in xrange(0, idx1):
            lightcurve1 = zfit[idx1, :]
            lightcurve2 = zfit[idx2, :]
            ccval = c_correlate(lightcurve1, lightcurve2)
            if sum(lightcurve1) != 0 and sum(lightcurve2) != 0:
                cmax = np.amax(ccval)
                cpeak = np.argmax(ccval) - (nxfit - 1) / 2
            else:
                cmax = 0
                cpeak = 0
            ccmax[idx2, idx1 - 1] = cmax
            ccpeak[idx2, idx1 - 1] = cpeak
            ya[idx2, idx1 - 1] = y[idx1 - 1]
            yv[idx2, idx1 - 1] = y[idx2]
            yidxa[idx2, idx1 - 1] = idx1 - 1
            yidxv[idx2, idx1 - 1] = idx2
            if idx1 - 1 != idx2:
                ccmax[idx1 - 1, idx2] = cmax
                ccpeak[idx1 - 1, idx2] = cpeak
                ya[idx1 - 1, idx2] = y[idx2]
                yv[idx1 - 1, idx2] = y[idx1 - 1]
                yidxa[idx1 - 1, idx2] = idx2
                yidxv[idx1 - 1, idx2] = idx1 - 1

    return {'zfit': zfit, 'ccmax': ccmax, 'ccpeak': ccpeak, 'x': x, 'nx': len(x), 'xfit': xfit, 'nxfit': nxfit, 'y': y,
            'ny': ny, 'yv': yv, 'ya': ya, 'yidxv': yidxv, 'yidxa': yidxa}


class ButtonsPlayCTRL():
    '''
    Produce A play/stop button widget for bokeh plot

    '''
    __slots__ = ['buttons']

    def __init__(self, plot_width=None, *args,
                 **kwargs):
        from bokeh.models import Button
        BUT_first = Button(label='<<', width=plot_width, button_type='primary')
        BUT_prev = Button(label='|<', width=plot_width, button_type='warning')
        BUT_play = Button(label='>', width=plot_width, button_type='success')
        BUT_next = Button(label='>|', width=plot_width, button_type='warning')
        BUT_last = Button(label='>>', width=plot_width, button_type='primary')
        self.buttons = [BUT_first, BUT_prev, BUT_play, BUT_next, BUT_last]


class FileDialog():
    '''
    produce a file dialog button widget for bokeh plot
    '''

    def __init__(self, plot_width=50, labels={'dir':'...','open':'open','save':'save'}, *args,
                 **kwargs):
        from bokeh.models import Button
        buttons = {}
        for k,v in labels.items():
            buttons[k] = Button(label=v, width=plot_width)
        self.buttons = buttons

    def askdirectory(self):
        Tkinter.Tk().withdraw()  # Close the root window
        in_path = tkFileDialog.askdirectory()
        if in_path:
            return in_path

    def askopenfilename(self):
        Tkinter.Tk().withdraw()  # Close the root window
        in_path = tkFileDialog.askopenfilename()
        if in_path:
            return in_path

    def asksaveasfilename(self):
        Tkinter.Tk().withdraw()  # Close the root window
        in_path = tkFileDialog.asksaveasfilename()
        if in_path:
            return in_path