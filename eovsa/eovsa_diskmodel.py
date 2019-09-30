from tqdm import tqdm
from taskinit import ms, tb, qa
from taskinit import iatool
from taskinit import cltool
from delmod_cli import delmod_cli as delmod
from clearcal_cli import clearcal_cli as clearcal
from suncasa.utils import mstools as mstl
from suncasa.utils import helioimage2fits as hf
import shutil, os
import sunpy.coordinates.ephemeris as eph
import numpy as np
from gaincal_cli import gaincal_cli as gaincal
from applycal_cli import applycal_cli as applycal
from uvsub_cli import uvsub_cli as uvsub
from split_cli import split_cli as split
from tclean_cli import tclean_cli as tclean
from ft_cli import ft_cli as ft


def read_ms(vis):
    ''' Read a CASA ms file and return a dictionary of amplitude, phase, uvdistance,
        uvangle, frequency (GHz) and time (MJD).  Currently only returns the XX IF channel.

        vis     Name of the visibility (ms) folder
    '''
    ms.open(vis)
    spwinfo = ms.getspectralwindowinfo()
    nspw = len(spwinfo.keys())
    for i in range(nspw):
        print('Working on spw', i)
        ms.selectinit(datadescid=0, reset=True)
        ms.selectinit(datadescid=i)
        if i == 0:
            spw = ms.getdata(['amplitude', 'phase', 'u', 'v', 'axis_info'], ifraxis=True)
            xxamp = spw['amplitude']
            xxpha = spw['phase']
            fghz = spw['axis_info']['freq_axis']['chan_freq'][:, 0] / 1e9
            band = np.ones_like(fghz) * i
            mjd = spw['axis_info']['time_axis']['MJDseconds'] / 86400.
            uvdist = np.sqrt(spw['u'] ** 2 + spw['v'] ** 2)
            uvang = np.angle(spw['u'] + 1j * spw['v'])
        else:
            spw = ms.getdata(['amplitude', 'phase', 'axis_info'], ifraxis=True)
            xxamp = np.concatenate((xxamp, spw['amplitude']), 1)
            xxpha = np.concatenate((xxpha, spw['phase']), 1)
            fg = spw['axis_info']['freq_axis']['chan_freq'][:, 0] / 1e9
            fghz = np.concatenate((fghz, fg))
            band = np.concatenate((band, np.ones_like(fg) * i))
    ms.close()
    return {'amp': xxamp, 'phase': xxpha, 'fghz': fghz, 'band': band, 'mjd': mjd, 'uvdist': uvdist, 'uvangle': uvang}


def fit_diskmodel(out, bidx, rstn_flux, uvfitrange=[1, 150], angle_tolerance=np.pi / 2, doplot=True):
    ''' Given the result returned by read_ms(), plots the amplitude vs. uvdistance
        separately for polar and equatorial directions rotated for P-angle, then overplots
        a disk model for a disk enlarged by eqfac in the equatorial direction, and polfac
        in the polar direction.  Also requires the RSTN flux spectrum for the date of the ms,
        determined from (example for 2019-09-01):
           import rstn
           frq, flux = rstn.rd_rstnflux(t=Time('2019-09-01'))
           rstn_flux = rstn.rstn2ant(frq, flux, out['fghz']*1000, t=Time('2019-09-01'))

    '''
    from util import bl2ord, lobe
    import matplotlib.pylab as plt
    import sun_pos
    from scipy.special import j1
    import scipy.constants
    mperns = scipy.constants.c / 1e9  # speed of light in m/ns
    # Rotate uv angle for P-angle
    pa, b0, r = sun_pos.get_pb0r(out['mjd'][0], arcsec=True)
    uvangle = lobe(out['uvangle'] - pa * np.pi / 180.)
    a = 2 * r * np.pi ** 2 / (180. * 3600.)  # Initial scale for z, uses photospheric radius of the Sun
    if doplot: f, ax = plt.subplots(3, 1)
    uvmin, uvmax = uvfitrange
    uvdeq = []
    uvdpol = []
    ampeq = []
    amppol = []
    zeq = []
    zpol = []
    # Loop over antennas 1-4
    antmax = 7
    at = angle_tolerance
    for i in range(4):
        fidx, = np.where(out['band'] == bidx)  # Array of frequency indexes for channels in this band
        for j, fi in enumerate(fidx):
            amp = out['amp'][0, fi, bl2ord[i, i + 1:antmax]].flatten() / 10000.  # Convert to sfu
            # Use only non-zero amplitudes
            good, = np.where(amp != 0)
            amp = amp[good]
            uva = uvangle[bl2ord[i, i + 1:antmax]].flatten()[good]
            # Equatorial points are within +/- pi/8 of solar equator
            eq, = np.where(np.logical_or(np.abs(uva) < at / 2, np.abs(uva) >= np.pi - at / 2))
            # Polar points are within +/- pi/8 of solar pole
            pol, = np.where(np.logical_and(np.abs(uva) >= np.pi / 2 - at / 2, np.abs(uva) < np.pi / 2 + at / 2))
            uvd = out['uvdist'][bl2ord[i, i + 1:antmax]].flatten()[good] * out['fghz'][fi] / mperns  # Wavelengths
            # Add data for this set of baselines to global arrays
            uvdeq.append(uvd[eq])
            uvdpol.append(uvd[pol])
            ampeq.append(amp[eq])
            amppol.append(amp[pol])
            zeq.append(uvd[eq])
            zpol.append(uvd[pol])
    uvdeq = np.concatenate(uvdeq)
    uvdpol = np.concatenate(uvdpol)
    uvdall = np.concatenate((uvdeq, uvdpol))
    ampeq = np.concatenate(ampeq)
    amppol = np.concatenate(amppol)
    ampall = np.concatenate((ampeq, amppol))
    zeq = np.concatenate(zeq)
    zpol = np.concatenate(zpol)
    zall = np.concatenate((zeq, zpol))
    # These indexes are for a restricted uv-range to be fitted
    ieq, = np.where(np.logical_and(uvdeq > uvmin, uvdeq <= uvmax))
    ipol, = np.where(np.logical_and(uvdpol > uvmin, uvdpol <= uvmax))
    iall, = np.where(np.logical_and(uvdall > uvmin, uvdall <= uvmax))
    if doplot:
        # Plot all of the data points
        ax[0].plot(uvdeq, ampeq, 'k+')
        ax[1].plot(uvdpol, amppol, 'k+')
        ax[2].plot(uvdall, ampall, 'k+')
        # Overplot the fitted data points in a different color
        ax[0].plot(uvdeq[ieq], ampeq[ieq], 'b+')
        ax[1].plot(uvdpol[ipol], amppol[ipol], 'b+')
        ax[2].plot(uvdall[iall], ampall[iall], 'b+')
    # Minimize ratio of points to model
    ntries = 300
    solfac = np.linspace(1.0, 1.3, ntries)
    d2m_eq = np.zeros(ntries, np.float)
    d2m_pol = np.zeros(ntries, np.float)
    d2m_all = np.zeros(ntries, np.float)
    sfac = np.zeros(ntries, np.float)
    sfacall = np.zeros(ntries, np.float)
    # Loop over ntries (300) models of solar disk size factor ranging from 1.0 to 1.3 r_Sun
    for k, sizfac in enumerate(solfac):
        eqpts = rstn_flux[fidx][0] * 2 * np.abs(j1(a * sizfac * zeq[ieq]) / (a * sizfac * zeq[ieq]))
        polpts = rstn_flux[fidx[0]] * 2 * np.abs(j1(a * sizfac * zpol[ipol]) / (a * sizfac * zpol[ipol]))
        sfac[k] = (np.nanmedian(ampeq[ieq] / eqpts) + np.nanmedian(amppol[ipol] / polpts)) / 2
        eqpts = rstn_flux[fidx[0]] * (2 * sfac[k]) * np.abs(j1(a * sizfac * zeq[ieq]) / (a * sizfac * zeq[ieq]))
        polpts = rstn_flux[fidx[0]] * (2 * sfac[k]) * np.abs(j1(a * sizfac * zpol[ipol]) / (a * sizfac * zpol[ipol]))
        allpts = rstn_flux[fidx[0]] * (2 * sfac[k]) * np.abs(j1(a * sizfac * zall[iall]) / (a * sizfac * zall[iall]))
        sfacall[k] = np.nanmedian(ampall[iall] / allpts)
        d2m_eq[k] = np.nanmedian(abs(ampeq[ieq] / eqpts - 1))
        d2m_pol[k] = np.nanmedian(abs(amppol[ipol] / polpts - 1))
        d2m_all[k] = np.nanmedian(abs(ampall[iall] / allpts - 1))
    keq = np.argmin(d2m_eq)
    kpol = np.argmin(d2m_pol)
    kall = np.argmin(d2m_all)
    eqradius = solfac[keq] * r
    polradius = solfac[kpol] * r
    allradius = solfac[kall] * r
    sfactor = sfac[keq]
    sfall = sfacall[kall]
    sflux = sfall * rstn_flux[fidx[0]]
    if doplot:
        z = np.linspace(1.0, 1000.0, 10000)
        # Overplot the best fit
        ax[0].plot(z, rstn_flux[fidx[0]] * (2 * sfactor) * np.abs(j1(a * solfac[keq] * z) / (a * solfac[keq] * z)))
        ax[1].plot(z, rstn_flux[fidx[0]] * (2 * sfactor) * np.abs(j1(a * solfac[kpol] * z) / (a * solfac[kpol] * z)))
        ax[2].plot(z, rstn_flux[fidx[0]] * (2 * sfall) * np.abs(j1(a * solfac[kall] * z) / (a * solfac[kall] * z)))
        # ax[1].plot(zpol,polpts,'y.')
        ax[0].set_title(
            str(out['fghz'][fidx][0])[:4] + 'GHz. R_eq:' + str(eqradius)[:6] + '". R_pol' + str(polradius)[:6]
            + '". R_all' + str(allradius)[:6] + '". Flux scl fac:' + str(sfall)[:4])
        # ax[0].plot(uvdeq,ampeq/eqpts,'k+')
        # ax[0].plot([0,1000],np.array([1,1])*np.nanmedian(ampeq/eqpts))
        # ax[1].plot(uvdpol,amppol/polpts,'k+')
        # ax[1].plot([0,1000],np.array([1,1])*np.nanmedian(amppol/polpts))
        for i in range(3):
            ax[i].set_xlim(0, 1000)
            ax[i].set_ylim(0.01, rstn_flux[fidx[0]] * 2 * sfactor)
            ax[i].set_yscale('log')
            ax[2].set_xlabel('UV Distance (wavelengths)')
            ax[i].set_ylabel('Amplitude (sfu)')
            ax[i].text(850, 125, ['Equator', 'Pole', 'All'][i])
    return bidx, out['fghz'][fidx[0]], eqradius, polradius, allradius, sfall, sflux


def fit_vs_freq(out):
    import matplotlib.pylab as plt
    import rstn
    from astropy.time import Time
    t = Time(out['mjd'][0], format='mjd')
    frq, flux = rstn.rd_rstnflux(t=t)
    rstn_flux = rstn.rstn2ant(frq, flux, out['fghz'] * 1000, t=t)
    band = []
    fghz = []
    eqrad = []
    polrad = []
    allrad = []
    sfac = []
    sflux = []
    for i in range(50):
        uvfitrange = np.array([10, 150]) + np.array([1, 18]) * i
        a, b, c, d, e, f, g = fit_diskmodel(out, i, rstn_flux, uvfitrange=uvfitrange, angle_tolerance=np.pi / 2,
                                            doplot=False)
        band.append(a)
        fghz.append(b)
        eqrad.append(c)
        polrad.append(d)
        allrad.append(e)
        sfac.append(f)
        sflux.append(g)
        if (i % 10) == 0: print(i)
    result = {'band': np.array(band), 'fghz': np.array(fghz), 'eqradius': np.array(eqrad),
              'polradius': np.array(polrad),
              'radius': np.array(allrad), 'flux_correction_factor': np.array(sfac), 'disk_flux': np.array(sflux) * 2.}
    plt.figure()
    plt.plot(result['fghz'], result['eqradius'], 'o', label='Equatorial Radius')
    plt.plot(result['fghz'], result['polradius'], 'o', label='Polar Radius')
    plt.plot(result['fghz'], result['radius'], 'o', label='Circular Radius')
    plt.legend()
    plt.xlabel('Frequency [GHz]')
    plt.ylabel('Radius [arcsec]')
    plt.title('Frequency-dependent Solar Disk Size for 2019-Sep-01')
    return result


def diskmodel(outname='disk', bdwidth='325MHz', direction='J2000 10h00m00.0s 20d00m00.0s',
              reffreq='2.8GHz', flux=660000.0, eqradius='16.166arcmin', polradius='16.166arcmin',
              pangle='21.1deg', index=None, cell='2.0arcsec', overwrite=True):
    ''' Create a blank solar disk model image (or optionally a data cube)

        outname       String to use for part of the image and fits file names (default 'disk')
        direction     String specifying the position of the Sun in RA and Dec.  Default
                        means use the standard string "J2000 10h00m00.0s 20d00m00.0s"
        reffreq       The reference frequency to use for the disk model (the frequency at which
                        the flux level applies). Default is '2.8GHz'.
        flux          The flux density, in Jy, for the entire disk. Default is 66 sfu.
        eqradius      The equatorial radius of the disk.  Default is
                        16 arcmin + 10" (for typical extension of the radio limb)
        polradius     The polar radius of the disk.  Default is
                        16 arcmin + 10" (for typical extension of the radio limb)
        pangle        The solar P-angle (geographic position of the N-pole of the Sun) in
                        degrees E of N.  This only matters if eqradius != polradius
        index         The spectral index to use at other frequencies.  Default None means
                        use a constant flux density for all frequencies.
        cell          The cell size (assumed square) to use for the image.  The image size
                        is determined from a standard radius of 960" for the Sun, divided by
                        cell size, increased to nearest power of 512 pixels. The default is '2.0arcsec',
                        which results in an image size of 1024 x 1024.
        Note that the frequency increment used is '325MHz', which is the width of EOVSA bands
          (not the width of individual science channels)
    '''

    diskim = outname + reffreq + '.im'
    if os.path.exists(diskim):
        if overwrite:
            os.system('rm -rf {}'.format(diskim))
        else:
            return diskim

    ia = iatool()
    cl = cltool()
    cl.done()
    ia.done()

    try:
        aspect = 1.01  # Enlarge the equatorial disk by 1%
        eqradius = qa.quantity(eqradius)
        diamajor = qa.quantity(2 * aspect * eqradius['value'], eqradius['unit'])
        polradius = qa.quantity(polradius)
        diaminor = qa.quantity(2 * polradius['value'], polradius['unit'])
        solrad = qa.convert(polradius, 'arcsec')
    except:
        print('Radius', eqradius, polradius,
              'does not have the expected format, number + unit where unit is arcmin or arcsec')
        return
    try:
        cell = qa.convert(qa.quantity(cell), 'arcsec')
        cellsize = float(cell['value'])
        diskpix = solrad['value'] * 2 / cellsize
        cell_rad = qa.convert(cell, 'rad')
    except:
        print('Cell size', cell, 'does not have the expected format, number + unit where unit is arcmin or arcsec')
        return

    # Add 90 degrees to pangle, due to angle definition in addcomponent() -- it puts the majoraxis vertical
    pangle = qa.add(qa.quantity(pangle), qa.quantity('90deg'))
    mapsize = ((int(diskpix) / 512) + 1) * 512
    # Flux density is doubled because it is split between XX and YY
    cl.addcomponent(dir=direction, flux=flux * 2, fluxunit='Jy', freq=reffreq, shape='disk',
                    majoraxis=diamajor, minoraxis=diaminor, positionangle=pangle)
    cl.setrefdirframe(0, 'J2000')

    ia.fromshape(diskim, [mapsize, mapsize, 1, 1], overwrite=True)
    cs = ia.coordsys()
    cs.setunits(['rad', 'rad', '', 'Hz'])
    cell_rad_val = cell_rad['value']
    cs.setincrement([-cell_rad_val, cell_rad_val], 'direction')
    epoch, ra, dec = direction.split()
    cs.setreferencevalue([qa.convert(ra, 'rad')['value'], qa.convert(dec, 'rad')['value']], type="direction")
    cs.setreferencevalue(reffreq, 'spectral')
    cs.setincrement(bdwidth, 'spectral')
    ia.setcoordsys(cs.torecord())
    ia.setbrightnessunit("Jy/pixel")
    ia.modify(cl.torecord(), subtract=False)
    ia.close()
    ia.done()
    # cl.close()
    cl.done()
    return diskim


def insertdiskmodel(vis, sizescale=1.0, fdens=None, dsize=None, overwrite_img_model=True):
    if fdens is None:
        # Default flux density for solar minimum
        fdens = np.array([891282, 954570, 1173229, 1245433, 1373730, 1506802,
                          1613253, 1702751, 1800721, 1946756, 2096020, 2243951,
                          2367362, 2525968, 2699795, 2861604, 3054829, 3220450,
                          3404182, 3602625, 3794312, 3962926, 4164667, 4360683,
                          4575677, 4767210, 4972824, 5211717, 5444632, 5648266,
                          5926634, 6144249, 6339863, 6598018, 6802707, 7016012,
                          7258929, 7454951, 7742816, 7948976, 8203206, 8411834,
                          8656720, 8908130, 9087766, 9410760, 9571365, 9827078,
                          10023598, 8896671])
    if dsize is None:
        # Default solar disk radius for solar minimum
        dsize = np.array(['1228.0arcsec', '1194.0arcsec', '1165.0arcsec', '1139.0arcsec', '1117.0arcsec',
                          '1097.0arcsec', '1080.0arcsec', '1065.0arcsec', '1053.0arcsec', '1042.0arcsec',
                          '1033.0arcsec', '1025.0arcsec', '1018.0arcsec', '1012.0arcsec', '1008.0arcsec',
                          '1003.0arcsec', '1000.0arcsec', '997.0arcsec', '994.0arcsec', '992.0arcsec',
                          '990.0arcsec', '988.0arcsec', '986.0arcsec', '985.0arcsec', '983.0arcsec', '982.0arcsec',
                          '980.0arcsec', '979.0arcsec', '978.0arcsec', '976.0arcsec', '975.0arcsec', '974.0arcsec',
                          '972.0arcsec', '971.0arcsec', '970.0arcsec', '969.0arcsec', '968.0arcsec', '967.0arcsec',
                          '966.0arcsec', '965.0arcsec', '964.0arcsec', '964.0arcsec', '963.0arcsec', '962.0arcsec',
                          '962.0arcsec', '961.0arcsec', '960.0arcsec', '959.0arcsec', '957.0arcsec', '956.0arcsec'])

    # Apply size scale adjustment (default is no adjustment)
    for i in range(len(dsize)):
        num, unit = dsize[i].split('arc')
        dsize[i] = str(float(num) * sizescale)[:6] + 'arc' + unit

    msfile = vis
    ms.open(msfile)
    diskim = []
    ms.open(msfile)
    spwinfo = ms.getspectralwindowinfo()
    nspw = len(spwinfo.keys())
    ms.close()
    diskimdir = 'diskim/'
    if not os.path.exists(diskimdir):
        os.makedirs(diskimdir)
    frq = []
    for sp in range(nspw):
        spw = spwinfo[str(sp)]
        frq.append('{:.4f}GHz'.format((spw['RefFreq'] + spw['TotalWidth'] / 2.0) / 1e9))
    frq = np.array(frq)
    tb.open(msfile + '/FIELD')
    phadir = tb.getcol('PHASE_DIR').flatten()
    tb.close()
    ra = phadir[0]
    dec = phadir[1]
    direction = 'J2000 ' + str(ra) + 'rad ' + str(dec) + 'rad'

    for sp in tqdm(range(nspw), desc='Generating {} disk models'.format(nspw), ascii=True):
        diskim.append(
            diskmodel(outname=diskimdir + 'disk{:02d}_'.format(sp), bdwidth=spwinfo[str(sp)], direction=direction,
                      reffreq=frq[sp],
                      flux=fdens[sp], eqradius=dsize[sp], polradius=dsize[sp], overwrite=overwrite_img_model))

    clearcal(msfile)
    delmod(msfile, otf=True, scr=True)

    mstl.clearflagrow(msfile, mode='clear')
    for sp in tqdm(range(nspw), desc='Inserting disk model', ascii=True):
        ft(vis=msfile, spw=str(sp), field='', model=str(diskim[sp]), nterms=1,
           reffreq="", complist="", incremental=False, usescratch=True)

    uvsub(vis=msfile)
    return msfile


def ant_trange(vis):
    ''' Figure out nominal times for tracking of old EOVSA antennas, and return time
        range in CASA format
    '''
    import eovsa_array as ea
    from astropy.time import Time
    # Get the Sun transit time, based on the date in the vis file name (must have UDByyyymmdd in the name)
    aa = ea.eovsa_array()
    date = vis.split('UDB')[-1][:8]
    slashdate = date[:4] + '/' + date[4:6] + '/' + date[6:8]
    aa.date = slashdate
    sun = aa.cat['Sun']
    mjd_transit = Time(aa.next_transit(sun).datetime(), format='datetime').mjd
    # Construct timerange based on +/- 3h55m from transit time (when all dishes are nominally tracking)
    trange = Time(mjd_transit - 0.1632, format='mjd').iso[:19] + '~' + Time(mjd_transit + 0.1632, format='mjd').iso[:19]
    trange = trange.replace('-', '/').replace(' ', '/')
    return trange


def disk_slfcal(vis, slfcaltbdir='./'):
    ''' Starting with the name of a calibrated ms (vis, which must have 'UDByyyymmdd' in the name)
        add a model disk based on the solar disk size for that date and perform multiple selfcal
        adjustments (two phase and one amplitude), and write out a final selfcaled database with
        the disk subtracted.  Returns the name of the final database.
    '''
    trange = ant_trange(vis)
    slashdate = trange[:10]
    # Verify that the vis is not in the current working directory
    if os.getcwd() == os.path.dirname(vis):
        print('Cannot copy vis file onto itself.')
        print('Please change to a different working directory')
        return None

    # Copy original ms to local directory
    shutil.copytree(vis, os.path.basename(vis))
    vis = os.path.basename(vis)

    # Default disk size measured for 2019/09/03
    defaultsize = np.array([990.6, 989.4, 988.2, 987.1, 986.0, 984.9, 983.8, 982.7, 981.7, 980.7,
                            979.7, 978.8, 977.8, 976.9, 976.0, 975.2, 974.3, 973.5, 972.7, 972.0,
                            971.2, 970.5, 969.8, 969.1, 968.5, 967.8, 967.2, 966.7, 966.1, 965.6,
                            965.1, 964.6, 964.1, 963.7, 963.3, 962.9, 962.5, 962.1, 961.8, 961.5,
                            961.3, 961.0, 960.8, 960.6, 960.4, 960.2, 960.1, 960.0, 959.9, 959.8])

    # Get current solar distance and modify the default size accordingly
    fac = eph.get_sunearth_distance('2019/09/03') / eph.get_sunearth_distance(slashdate)
    newsize = defaultsize * fac.to_value()
    dsize = np.array([str(i)[:5] + 'arcsec' for i in newsize])

    # Insert the disk model (msfile is the same as vis, and will be used as the "original" vis file name)
    msfile = insertdiskmodel(vis, dsize=dsize)

    tdate = mstl.get_trange(vis)[0].datetime.strftime('%Y%m%d')
    caltb = os.path.join(slfcaltbdir, tdate + '_1.pha')
    # Phase selfcal on the disk using solution interval "infinite"
    gaincal(vis=msfile, caltable=caltb, selectdata=True, uvrange="<3.0Klambda", antenna="0~12", solint="inf",
            combine="scan",
            refant="0", refantmode="flex", minsnr=1.0, gaintype="G", calmode="p", append=False)
    applycal(vis=msfile, selectdata=True, antenna="0~12", gaintable=caltb, interp="nearest", calwt=False,
             applymode="calonly")
    # Split corrected data and model to a new ms for round 2 of phase selfcal
    vis1 = 'slf_' + msfile
    mstl.splitX(msfile, outputvis=vis1, datacolumn="corrected", datacolumn2="model_data")

    caltb = os.path.join(slfcaltbdir, tdate + '_2.pha')
    # Second round of phase selfcal on the disk using solution interval "1min"
    gaincal(vis=vis1, caltable=caltb, selectdata=True, uvrange="<3.0Klambda", antenna="0~12", solint="1min",
            combine="scan",
            refant="0", refantmode="flex", minsnr=1.0, gaintype="G", calmode="p", append=False)
    applycal(vis=vis1, selectdata=True, antenna="0~12", gaintable=caltb, interp="nearest", calwt=False,
             applymode="calonly")
    # Split corrected data and model to a new ms
    vis2 = 'slf2_' + msfile
    mstl.splitX(vis, outputvis=vis2, datacolumn="corrected", datacolumn2="model_data")

    caltb = os.path.join(slfcaltbdir, tdate + '_3.amp')
    # Final round of amplitude selfcal with 1-h solution interval (restrict to 16-24 UT)
    gaincal(vis=vis2, caltable=caltb, selectdata=True, uvrange=">0.1Klambda", antenna="0~12&0~12",
            timerange=trange,
            solint="60min", combine="scan", refant="10", refantmode="flex", minsnr=1.0, gaintype="G", calmode="a",
            append=False)
    applycal(vis=vis2, selectdata=True, antenna="0~12", gaintable=caltb, interp="nearest", calwt=False,
             applymode="calonly")
    # Split out corrected data and model and do uvsub
    vis3 = 'slf3_' + msfile
    mstl.splitX(vis, outputvis=vis3, datacolumn="corrected", datacolumn2="model_data")
    uvsub(vis=vis3, reverse=False)

    # Final split to
    final = 'final_' + msfile
    split(vis3, outputvis=final, datacolumn='corrected')

    # Remove the interim ms files
    shutil.rmtree(vis)
    shutil.rmtree(vis1)
    shutil.rmtree(vis2)
    shutil.rmtree(vis3)

    # Return the name of the selfcaled ms
    return final


def fd_images(vis, cleanup=False, niter=None, imgoutdir='./'):
    ''' Create standard full-disk images in "images" subdirectory of the current directory.
        If cleanup is True, delete those images after completion, leaving only the fits images.
    '''
    # Check if "images" directory exists (if not, create it and mark it for later deletion)
    try:
        if os.stat('images'):
            rm_images = False  # Mark as not removeable
    except:
        os.mkdir('images')
        if cleanup:
            rm_images = True  # Mark as removeable
        else:
            rm_images = False  # Mark as not removeable

    trange = ant_trange(vis)
    tdate = trange.replace('/', '')[:8]
    if niter is None:
        niter = 5000
    spws = ['0~1', '2~5', '6~10', '11~20', '21~30', '31~43']
    imagefile = []
    fitsfile = []
    for spw in spws:
        spwstr = '-'.join(['{:02d}'.format(int(sp)) for sp in spw.split('~')])
        imname = "images/briggs" + spwstr
        tclean(vis=vis, selectdata=True, spw=spw, timerange=trange,
               antenna="0~12", datacolumn="corrected", imagename=imname, imsize=[1024], cell=['2.5arcsec'],
               stokes="XX", projection="SIN", specmode="mfs", interpolation="linear", deconvolver="multiscale",
               scales=[0, 5, 15, 30], nterms=2, smallscalebias=0.6, restoration=True, weighting="briggs", robust=0,
               niter=niter, gain=0.05, usemask="user", mask="box[[0pix,0pix],[1024pix,1024pix]]", savemodel="none")
        outfits = os.path.join(imgoutdir, 'eovsa_' + tdate + '.spw' + spwstr + '.tb.fits')
        imagefile.append(imname + '.image')
        fitsfile.append(outfits)
    hf.imreg(vis=vis, imagefile=imagefile, fitsfile=fitsfile, timerange=[trange] * len(fitsfile), toTb=True,
             overwrite=True)
    if rm_images:
        shutil.rmtree('images')  # Remove all images and the folder named images

    # To add disk model image to the images, I can try scipy.ndimage routines gaussian_filter() and zoom()


def feature_slfcal(vis, niter=200, slfcaltbdir='./'):
    ''' Uses images from disk-selfcaled data as model for further self-calibration of outer antennas.
        This is only a good idea if there are bright active regions that provide strong signal on the
        londer baselines.
    '''
    trange = ant_trange(vis)
    spws = ['0~1', '2~5', '6~10', '11~20', '21~30', '31~49']
    appends = [False, True, True, True, True, True]
    # Insert model into ms and do "inf" gaincal, appending to table each subsequent time

    tdate = mstl.get_trange(vis)[0].datetime.strftime('%Y%m%d')
    caltb = os.path.join(slfcaltbdir, tdate + '_d1.pha')
    for i, spw in enumerate(spws):
        imname = 'images/briggs' + spw.replace('~', '-') + '.model'
        if spw == '31~49':
            # The high-band image is only made to band 43, so adjust the name
            imname = 'images/briggs31-43.model'
        ft(vis=vis, spw=spw, model=imname, usescratch=True)
        gaincal(vis=vis, spw=spw, caltable=caltb, selectdata=True, timerange=trange, uvrange='>1Klambda',
                combine="scan",
                antenna='0~12&0~12', refant='10', solint='inf', gaintype='G', minsnr=1.0, calmode='p',
                append=appends[i])
    # Apply the corrections to the data and split to a new ms
    applycal(vis=vis, selectdata=True, antenna="0~12", gaintable=caltb, interp="nearest", calwt=False,
             applymode="calonly")
    vis1 = 'dslf1_' + vis
    split(vis, outputvis=vis1, datacolumn="corrected")

    caltb = os.path.join(slfcaltbdir, tdate + '_d2.pha')
    # Move the existing images directory so that a new one will be created
    shutil.move('images', 'old_images')
    # Make new model images for another round of selfcal
    fd_images(vis1, cleanup=False, niter=niter)
    for i, spw in enumerate(spws):
        imname = 'images/briggs' + spw.replace('~', '-') + '.model'
        if spw == '31~49':
            # The high-band image is only made to band 43, so adjust the name
            imname = 'images/briggs31-43.model'
        ft(vis=vis1, spw=spw, model=imname, usescratch=True)
        gaincal(vis=vis1, spw=spw, caltable=caltb, selectdata=True, timerange=trange, uvrange='>1Klambda',
                combine="scan",
                antenna='0~12&0~12', refant='10', solint='1min', gaintype='G', minsnr=1.0, calmode='p',
                append=appends[i])
    # Apply the corrections to the data and split to a new ms
    applycal(vis=vis1, selectdata=True, antenna="0~12", gaintable=caltb, interp="nearest", calwt=False,
             applymode="calonly")
    vis2 = 'dslf2' + vis
    split(vis1, outputvis=vis2, datacolumn="corrected")
    shutil.rmtree('images')  # Remove all images and the folder named images
    return vis2


def pipeline_run(vis, outputvis='', slfcaltbdir='./', imgoutdir='./'):
    import glob
    from astropy.io import fits

    if not os.path.exists(slfcaltbdir):
        os.makedirs(slfcaltbdir)
    # Generate calibrated visibility by self calibrating on the solar disk
    ms_slfcaled = disk_slfcal(vis, slfcaltbdir=slfcaltbdir)
    # Make initial images from self-calibrated visibility file, and check T_b max
    fd_images(ms_slfcaled, imgoutdir=imgoutdir)
    # Check if any of the images has a bright source (T_b > 300,000 K), and if so, remake images
    # with fewer components and execute feature_slfcal
    files = glob.glob('*.fits')
    bright = False
    for file in files:
        data = fits.getdata(file)
        data.shape = data.shape[-2:]  # gets rid of any leading axes of size 1
        if np.nanmax(np.nanmax(data)) > 300000:
            bright = True
            break
    if bright:
        # A bright source exists, so do feature self-calibration
        shutil.rmtree('images')
        fd_images(ms_slfcaled, niter=200, imgoutdir=imgoutdir)  # Does shallow clean for selfcal purposes
        ms_slfcaled2 = feature_slfcal(ms_slfcaled, slfcaltbdir=slfcaltbdir)  # Creates newly calibrated database
        fd_images(ms_slfcaled2, imgoutdir=imgoutdir)  # Does deep clean for final image creation
        # Cleanup of interim ms's would be done here...
        shutil.rmtree(ms_slfcaled)
        ms_slfcaled = ms_slfcaled2
    #  Final move of fits images can also be done here...
    if outputvis:
        os.system('mv {} {}'.format(ms_slfcaled, outputvis))
        ms_slfcaled = outputvis
    return ms_slfcaled