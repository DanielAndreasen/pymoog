#!/usr/bin/python
from __future__ import division, print_function
import numpy as np
from scipy.integrate import simps
from scipy import integrate
import scipy as sp
import scipy
from scipy.interpolate import interp1d, LinearNDInterpolator, griddata, interpn, InterpolatedUnivariateSpline
import gzip
import matplotlib.pyplot as plt


"""
Following the concept of Sz. Mezeros and C. Allende Prieto: For each set
of parameters, we identified the 8 immediate neighbors with higher and
lower values for each parameter in the grid, calculated by numerical
integration the Rosseland optical depth for each, re-sampled all the
thermodynamical quantities in the atmosphere (temperature, gas pressure,
and electron density) on a common optical depth scale for all models
by linear interpolation, and then interpolated, linearly, all the
thermodynamical quantities to the parameters (Teff , log g, and [Fe/H])
of the target model. Other quantities included in the models (Rosseland
opacities, radiative pressure, etc.) were also interpolated in the same
way.
"""

def _unpack_model(fname):
    """Unpack the compressed model and store it in a temporary file

    :fname: File name of the compressed atmosphere model
    :returns: String of the uncompressed atmosphere model
    """
    f = gzip.open(fname)
    return f.readlines()


def _read_header(fname):
    """Read the header of the model atmosphere

    :fname: file name of the model atmosphere
    :returns: Teff and number of layers

    """
    # Get information from the header
    teff, num_layers = None, None
    # with open(fname) as lines:
    for line in fname:
        vline = line.split()
        param = vline[0]
        if param == 'TEFF':
            teff = float(vline[1])
            logg = float(vline[3])
        elif param == "READ":
            num_layers = int(vline[2])
        # Exit the loop when we have what we need
        if teff and num_layers:
            return teff, num_layers


def save_model(model, type='kurucz95', fout='out.atm', vt=1.2):
    """Save the model atmosphere in the right format

    :model: The interpolated model atmosphere
    :type: Type of model atmosphere (onyl kurucz95 at the moment)
    :fout: Which place to save to
    """
    if type == 'kurucz95':
        header = 'KURUCZ\n'\
                 'Teff=%i   log g=%.2f   [Fe/H]=%.2f    vt=%.3e\n'\
                 'NTAU        %i' % (5777, 4.44, -0.14, 2.4e5, 72)
    elif type.lower() == 'marcz':  # How to spell this?
        raise NotImplementedError('Patience is the key. Wait a bit more for %s\
                                   models to be implemented.' % type)
    else:
        raise NameError('Could not find %s models' % type)

    footer = '    %.3e\n'\
             'NATOMS     1  %.2f\n'\
             '      26.0   %.2f\n'\
             'NMOL      19\n'\
             '      606.0    106.0    607.0    608.0    107.0    108.0    112.0  707.0\n'\
             '       708.0    808.0     12.1  60808.0  10108.0    101.0     6.1    7.1\n'\
             '         8.1    822.0     22.1' % (vt*1e5, -0.2, 7.47-0.2)

    np.savetxt(fout, model.T, header=header, footer=footer, comments='',
               delimiter=' ',
               fmt=('%15.8E', '%8.1f', '%.3E', '%.3E', '%.3E', '%.3E', '%.3E'))


def tauross_scale(abross, rhox, num_layers):
    """Build the tau-ross scale

    :abross: absorption
    :rhox: density
    :num_layers: Number of layers in the model atmosphere
    :returns: the new tau-ross scale
    """

    tauross = sp.integrate.cumtrapz(rhox * abross, initial=rhox[0] * abross[0])

    # tauross = np.zeros(num_layers)
    # This is supposed to be the first element
    # tauross[0] = abross[0] * rhox[0]
    # for i in range(2, num_layers+1):
        # tauross[i-1] = sp.integrate.simps(rhox[0:i], abross[0:i], even='last')
        # tauross[i-1] = np.trapz(rhox[0:i], abross[0:i])

    return tauross

def int_newton_cotes(x,f,p=5):
    def newton_cotes(x, f):
        if x.shape[0] < 2:
            return 0
        rn = (x.shape[0]-1)*(x-x[0])/(x[-1]-x[0])
        # Just making sure ...
        rn[0]= 0
        rn[-1]= len(rn)-1
        weights= integrate.newton_cotes(rn)[0]
        return (x[-1]-x[0])/(x.shape[0]-1)*np.dot(weights,f)
    ret = 0
    for indx in range(0,x.shape[0],p-1):
        ret+= newton_cotes(x[indx:indx+p],f[indx:indx+p])
    return ret

def rosslandtau(abross, rhox, num_layers, force=True):
        """Calculate the Rossland mean optical depth"""
        if force:
            rtau= np.zeros(num_layers)
            for ii in range(1,num_layers):
                rtau[ii]= int_newton_cotes(rhox[:ii+1],
                                           abross[:ii+1])
            rtau+= rhox[0]*abross[0]
        else:
            rtau= 10.**(np.linspace(-6.875,2.,num_layers))
        return rtau



def read_model(filename):
    """Read the model, return all the columns and tauross"""

    teff, num_layers = _read_header(filename)

    # This are the thermodynamical quantities.
    model = np.genfromtxt(filename, skiprows=23, skip_footer=2,
                          usecols=(0, 1, 2, 3, 4, 5, 6),
                          names=['RHOX', 'T', 'P', 'XNE', 'ABROSS',
                                 'ACCRAD', 'VTURB'])

    # TODO: Can this even happen? Any way, a better error would be helpful :)
    if len(model) != num_layers:
            raise Exception("FORMAT ERROR")

    model_rhox = model['RHOX']
    model_t = model['T']
    model_p = model['P']
    model_xne = model['XNE']
    model_abross = model['ABROSS']
    model_accrad = model['ACCRAD']
    # TODO: We don't need this one. manual p. 17
    model_vturb = model['VTURB']

    #tauross = tauross_scale(model_abross, model_rhox, num_layers)
    #print (tauross)
    #print (rosslandtau(model_abross, model_rhox, num_layers))
    tauross = rosslandtau(model_abross, model_rhox, num_layers)
    return (model_rhox, model_t, model_p, model_xne, model_abross,
            model_accrad, model_vturb, tauross)

    #f = _unpack_model("/home/daniel/Documents/Uni/phdproject/programs/pymoog/kurucz95/p00/5000g40.p00.gz")
    #read_model(f)

def interp_model(tauross, model, tauross_new):
    """Interpolate a physical quantity from the model from the tauross scale to
    1 value of the new tauross scale

    :tauross: Old tauross scale
    :model: Column in the atmospheric model to be interpolated
    :tauross_new: New tauross scale
    :returns: The interpolated atmospheric model to the new scale
    """
    # Extra key-words speed up the function with a factor of 10!
    f = interp1d(tauross, model, assume_sorted=True, copy=False)
    #f = InterpolatedUnivariateSpline(tauross,model,k=3)
    return f(tauross_new)


def interpolator(models, teff, logg, feh, out='out.atm'):
    """The function to call from the main program (pymoog.py or main.py)

    :models: As generated from _get_models
    :out: The interpolated model saved in this file
    """
    # TODO: Need to be able to use e.g. 4 Teff models (16 models in total)
    # NOTE: Run pymoog.py instead. Now this is only functions (more or less)

    teff, nteff = teff
    logg, nlogg = logg
    feh, nfeh = feh

    mapteff = (teff - nteff[1]) / (nteff[0] - nteff[1])
    maplogg = (logg - nlogg[1]) / (nlogg[0] - nlogg[1])
    mapmetal = (feh - nfeh[1]) / (nfeh[0] - nfeh[1])
#    print(mapteff)
#    print(maplogg) 
#    print(mapmetal)   

    tauross_all = []
    model_all = []
    for model in models:
        read = _unpack_model(model)
        columns = read_model(read)
        tauross = columns[-1]
        tauross_all.append(tauross)
        model_all.append(columns[0:-1])

    tauross = tauross_all[0]
    layers = len(tauross)
    columns = len(model_all[0])

    tauross_min = min([v[-1] for v in tauross_all])
    tauross_max = max([v[0] for v in tauross_all])
    tauross_tmp = tauross[(tauross >= tauross_max) & (tauross <= tauross_min)]
    f = interp1d(range(len(tauross_tmp)), tauross_tmp)
    #ALTERNATIVE INTERPOLATION ITS MORE OR LESS EQUAL
    #f = InterpolatedUnivariateSpline(range(len(tauross_tmp)), tauross_tmp,k=3)
    tauross_new = f(np.linspace(0, len(tauross_tmp) - 1, layers))
    
   #Attempt to renormalize tau_ross
   # tauross_new=tauross_new/np.max(tauross_tmp) 
   # print(tauross_new)
   #FAILED!

    # Do the interpolation over the models
    grid = np.zeros((4, 2, 2, columns))
    model_out = np.zeros((columns, layers))
    plm = np.array(([0, 1], [0, 1]))
    pt = np.array(([0, 0.33, 0.66, 1]))
    plx = np.array(([0, 0.33, 0.66, 1], [0, 1], [0, 1]))
    xi = np.array((mapteff, maplogg, mapmetal))
    #Maybe the for loop over the layers is not necessary since the interp_model function does that?
    for layer in range(layers):
        tau_layer = tauross_new[layer]
        
        for column in range(columns):

            # For 2x2x2
            # grid[0, 0, 0, column] = interp_model(tauross_all[0], model_all[0][column], tau_layer)
            # grid[0, 1, 0, column] = interp_model(tauross_all[1], model_all[1][column], tau_layer)
            # grid[1, 0, 0, column] = interp_model(tauross_all[2], model_all[2][column], tau_layer)
            # grid[1, 1, 0, column] = interp_model(tauross_all[3], model_all[3][column], tau_layer)

            # grid[0, 0, 1, column] = interp_model(tauross_all[4], model_all[4][column], tau_layer)
            # grid[0, 1, 1, column] = interp_model(tauross_all[5], model_all[5][column], tau_layer)
            # grid[1, 0, 1, column] = interp_model(tauross_all[6], model_all[6][column], tau_layer)
            # grid[1, 1, 1, column] = interp_model(tauross_all[7], model_all[7][column], tau_layer)

            # For 4x2x2
            grid[0, 0, 0, column] = interp_model(tauross_all[0], model_all[0][column], tau_layer)
            grid[0, 1, 0, column] = interp_model(tauross_all[1], model_all[1][column], tau_layer)
            grid[1, 0, 0, column] = interp_model(tauross_all[2], model_all[2][column], tau_layer)
            grid[1, 1, 0, column] = interp_model(tauross_all[3], model_all[3][column], tau_layer)

            grid[2, 0, 0, column] = interp_model(tauross_all[4], model_all[4][column], tau_layer)
            grid[2, 1, 0, column] = interp_model(tauross_all[5], model_all[5][column], tau_layer)
            grid[3, 0, 0, column] = interp_model(tauross_all[6], model_all[6][column], tau_layer)
            grid[3, 1, 0, column] = interp_model(tauross_all[7], model_all[7][column], tau_layer)

            grid[0, 0, 1, column] = interp_model(tauross_all[12], model_all[12][column], tau_layer)
            grid[0, 1, 1, column] = interp_model(tauross_all[13], model_all[13][column], tau_layer)
            grid[1, 0, 1, column] = interp_model(tauross_all[14], model_all[14][column], tau_layer)
            grid[1, 1, 1, column] = interp_model(tauross_all[15], model_all[15][column], tau_layer)

            grid[2, 0, 1, column] = interp_model(tauross_all[8], model_all[8][column], tau_layer)
            grid[2, 1, 1, column] = interp_model(tauross_all[9], model_all[9][column], tau_layer)
            grid[3, 0, 1, column] = interp_model(tauross_all[10], model_all[10][column], tau_layer)
            grid[3, 1, 1, column] = interp_model(tauross_all[11], model_all[11][column], tau_layer)


###########################
#New attempt using ndimage#
#####UNDER CONSTRUCTION####
###########################
            
           #input_map = grid.reshape(4,2,2

###########################
###########################

            model_out[column,layer] = interpn(plx, grid[:,:,:,column], xi)
    #print (model_out)
            # TODO: Interpolate first temperature and then the other
            # Temperature should be cubic, while the others are linear
            #for i in range(2):
            #    for j in range(2):
            #        model_out[column, layer] = interpn(pt, grid[:, i, j,  column], mapteff) #, method='splinef2d')
            #for i in range(4):
            #    model_out[column, layer] = interpn(plm, grid[i, :, :, column],
            #            xi[1:])







    # TODO: Possible remove this below at some point
    return model_all, model_out, column
