#!/usr/bin/env python
# -*- coding: utf8 -*-

# My imports
from __future__ import division, print_function
import logging
import os
from shutil import copyfile
import yaml
import numpy as np
from utils import GetModels, _update_par_synth
from interpolation import interpolator
from interpolation import save_model
from utils import _run_moog
from observations import read_observations, plot_synth, plot_synth_obs, plot, chi2
import seaborn

def _getSpt(spt):
    """Get the spectral type from a string like 'F5V'."""
    if len(spt) > 4:
        raise ValueError('Spectral type most be of the form: F8V')
    if '.' in spt:
        raise ValueError('Do not use half spectral types as %s' % spt)
    with open('SpectralTypes.yml', 'r') as f:
        d = yaml.safe_load(f)
    temp = spt[0:2]
    lum = spt[2:]
    try:
        line = d[lum][temp]
    except KeyError:
        print('Was not able to find the spectral type: %s' % spt)
        print('Teff=5777 and logg=4.44')
        return 5777, 4.44
    try:
        line = line.split()
        teff = int(line[0])
        logg = float(line[1])
    except AttributeError:
        teff = line
        logg = 4.44
    return teff, logg


def _getMic(teff, logg, feh):
    """Calculate micro turbulence."""
    if logg >= 3.95:  # Dwarfs Tsantaki 2013
        mic = 6.932 * teff * (10**(-4)) - 0.348 * logg - 1.437
        return round(mic, 2)
    else:  # Giants Adibekyan 2015
        mic = 2.72 - (0.457 * logg) + (0.072 * feh)
        return round(mic, 2)


def _options(options=None):
    '''Reads the options inside the config file'''
    defaults = {'spt': False,
                'model': 'kurucz95',
                'MOOGv': 2014,
                'plotpars': 1,
                'plot': False,  #This is irrelevant with the batch.par value
                'step_wave': 0.01,
                'step_flux': 5.0,
                'observations': False,
                'resolution': 0.06,
                'vmac': 0.0,
                'vsini': 0.0,
                'limb': 0.0,
                'lorentz': 0.0
                }
    if not options:
        return defaults
    else:
        for option in options.split(','):
            if ':' in option:
                option = option.split(':')
                defaults[option[0]] = option[1]
            else:
                # Clever way to change the boolean
                if option in ['teff', 'logg', 'feh', 'vt']:
                    option = 'fix_%s' % option
                defaults[option] = False if defaults[option] else True
        defaults['model'] = defaults['model'].lower()
        defaults['step_wave'] = float(defaults['step_wave'])
        defaults['step_flux'] = float(defaults['step_flux'])
        defaults['plotpars'] = int(defaults['plotpars'])
        #defaults['plot'] = int(defaults['plot'])
        #defaults['observations'] = str(defaults['observations'])
        defaults['resolution'] = float(defaults['resolution'])
        defaults['vmac'] = float(defaults['vmac'])
        defaults['vsini'] = float(defaults['vsini'])
        defaults['limb'] = float(defaults['limb'])
        defaults['lorentz'] = float(defaults['lorentz'])
        defaults['MOOGv'] = int(defaults['MOOGv'])
        return defaults

def read_wave(linelist): 
    """Read the wavelenth intervals of the line list"""

    with open(linelist, 'r') as f:

        lines = f.readlines()
    first_line = lines[0].split()

    if len(first_line) == 1: 
        start_wave = first_line[0].split('-')[0]
        end_wave = first_line[0].split('-')[1]
    else:
        start_wave = first_line[0]
        end_wave = lines[-1].split()[0]
    return start_wave, end_wave  

def read_linelist(fname):
    """Read the file that contains the line list then read the lines"""

    with open('linelist/%s' % fname, 'r') as f:

        lines = f.readlines()

    n_intervals = len(lines)
    ranges = []
    flines = []
    for line in lines:
        line = line.split()
        # Check if linelist files are inside the directory, if not break
        if not os.path.isfile('linelist/%s' % line[0]):
            raise IOError('The linelist is not in the linelist directory!')
        flines.append(line[0])

        with open('linelist/%s' % line[0], 'r') as f:

            lines = f.readlines()
        first_line = lines[0].split()

        if len(first_line) == 1: 
            start_wave = first_line[0].split('-')[0]
            end_wave = first_line[0].split('-')[1]
            r = (float(start_wave), float(end_wave))
            ranges.append(r)
        else:
            start_wave = first_line[0]
            end_wave = lines[-1].split()[0]
            r = (float(start_wave), float(end_wave))
            ranges.append(r)
    return n_intervals, ranges, flines


def read_specintervals(obs_fname, N, r):
    """Read only the spectral chunks from the observed spectrum"""
    x_obs = []
    y_obs = []
    for i in range(N):
        x, y = read_observations(obs_fname, start_synth=r[i][0], end_synth=r[i][1])
        x_obs.append(x)
        y_obs.append(y)
    return x_obs, y_obs

def create_model(initial, linelist, options):
    """Create synthetic spectrum"""

    # TODO: Fix the interpolation please!
    if initial[1] > 4.99:  # quick fix
        initial[1] = 4.99
    grid = GetModels(teff=initial[0], logg=initial[1], feh=initial[2], atmtype=options['model'])
    models, nt, nl, nf = grid.getmodels()
    inter_model = interpolator(models,
                               teff=(initial[0], nt),
                               logg=(initial[1], nl),
                               feh=(initial[2], nf))
    save_model(inter_model, params=initial)

    #Insert linelist to batch.par
    N, r, f = read_linelist(linelist)
    for i in range(N):
        _update_par_synth('linelist/%s' % f[i], r[i][0], r[i][1], options=options)
        _run_moog(driver='synth')
    return

def synthdriver(starLines='StarMe_synth.cfg', overwrite=False):
    """The function that glues everything together

    Input:
    starLines   -   Configuration file (default: StarMe.cfg)
    parfile     -   The configuration file for MOOG
    model       -   Type of model atmospheres
    plot        -   Plot results (currently not implemented)

    Output:
    <linelist>.(NC).out     -   NC=not converget.
    results.csv             -   Easy readable table with results from many linelists
    """
    try:  # Cleaning from previous runs
        os.remove('captain.log')
    except OSError:
        pass
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler('captain.log')
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Check if there is a directory called linelist, if not create it and ask the user to put files there
    if not os.path.isdir('linelist'):
        logger.error('Error: The directory linelist does not exist!')
        os.mkdir('linelist')
        logger.info('linelist directory was created')
        raise IOError('linelist directory did not exist! Put the linelists inside that directory, please.')

    # Create results directory
    if not os.path.isdir('results'):
        os.mkdir('results')
        logger.info('results directory was created')

    with open(starLines, 'r') as lines:
        for line in lines:
            if not line[0].isalpha():
                logger.debug('Skipping header: %s' % line.strip())
                continue
            logger.info('Line list: %s' % line.strip())
            line = line.strip()
            line = line.split(' ')

            #Check if configuration parameters are correct
            if len(line) not in [1, 2, 5, 6]:
                logger.error('Could not process this information: %s' % line)
                continue

            # Check if the linelist is inside the directory, if not log it and pass to next linelist
            if not os.path.isfile('linelist/%s' % line[0]):
                logger.error('Error: linelist/%s not found.' % line[0])
                continue

            if len(line) == 1:
                initial = [5777, 4.44, 0.00, 1.00]
                options = _options()
                plot_flag = False
                x_obs, y_obs = (None, None)
                logger.info('Getting initial model grid')
                create_model(initial, line[0], options)
                logger.info('Interpolation successful.')
                logger.info('Setting solar values {0}, {1}, {2}, {3}'.format(*initial))

            elif len(line) == 2:
                options = _options(line[1])
                if options['spt']:
                    logger.info('Spectral type given: %s' % line[1])
                    Teff, logg = _getSpt(options['spt'])
                    mic = _getMic(Teff, logg)
                    initial = (Teff, logg, 0.00, mic)
                else:
                    initial = [5777, 4.44, 0.00, 1.00]

                if options['observations']:
                    # Check if observations exit, if not pass another line         
                    if not (os.path.isfile('spectra/%s' % options['observations']) and os.path.isfile(options['observations'])):
                        logger.error('Error: %s not found.' % options['observations'])
                        continue

                    print('This is your observed spectrum: %s' % options['observations'])
                    N, r, f = read_linelist(line[0])
                    x_obs, y_obs = read_specintervals('spectra/%s' % options['observations'], N, r)
                else:
                    x_obs, y_obs = (None, None)

                logger.info('Getting initial model grid')
                create_model(initial, line[0], options)
                logger.info('Interpolation successful.')
                logger.info('Initial parameters: {0}, {1}, {2}, {3}'.format(*initial))

                if options['plot']: #if there in no observed only the synthetic will be plotted #need to create function to read the synthetic #does not work now
                    plot(x_obs, y_obs, x, y)

            elif len(line) == 5:
                logger.info('Initial parameters given by the user.')
                initial = map(float, line[1::])
                initial[0] = int(initial[0])
                options = _options()
                x_obs, y_obs = (None, None) #No observed spectrum 
                logger.info('Initial parameters: {0}, {1}, {2}, {3}'.format(*initial))
                logger.info('Getting initial model grid')
                create_model(initial, line[0], options)
                logger.info('Interpolation successful.')

            elif len(line) == 6:
                logger.info('Initial parameters given by user.')
                initial = map(float, line[1:-1])
                initial[0] = int(initial[0])
                logger.info('Initial parameters: {0}, {1}, {2}, {3}'.format(*initial))
                options = _options(line[-1])

                if options['observations']:
                    # Check if observations exit, if not pass another line         
                    if not (os.path.isfile('spectra/%s' % options['observations']) and os.path.isfile(options['observations'])):
                        logger.error('Error: %s not found.' % options['observations'])
                        continue

                    print('This is your observed spectrum: %s' % options['observations'])
                    N, r, f = read_linelist(line[0])
                    x_obs, y_obs = read_specintervals('spectra/%s' % options['observations'], N, r)
                else:
                    x_obs, y_obs = (None, None)

                logger.info('Getting initial model grid')
                create_model(initial, line[0], options)
                logger.info('Interpolation successful.')
                logger.info('Initial parameters: {0}, {1}, {2}, {3}'.format(*initial))

                if options['plot']: #if there in no observed only the synthetic will be plotted #need to create function to read the synthetic #does not work now
                    plot(x_obs, y_obs, x, y)

            else:
                logger.error('Could not process information for this line list: %s' % line)
                continue

            if options['model'] != 'kurucz95' and options['model'] != 'apogee_kurucz' and options['model'] != 'marcs':
                logger.error('Your request for type: %s is not available' % model)
                continue

            logger.info('Starting the minimization procedure...')

            # Options not in use will be removed
            if __name__ == '__main__':
                options['GUI'] = False  # Running batch mode
            else:
                options['GUI'] = True  # Running GUI mode
            options.pop('spt')

            N, r, f = read_linelist(line[0])
            print('%s synthetic sṕectra were created. Check the results/ folder.' % N)

    return

if __name__ == '__main__':
    synthdriver(starLines='StarMe_synth.cfg', overwrite=False)
