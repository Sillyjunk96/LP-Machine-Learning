import json
from time import time
from math import pi
import os
import sys
import numpy as np
from outcar_parser import Parser
from configuration import Configuration
import kernel


def load_data(u_conf: dict, offset=0) ->  (int, int, np.array, list):
    '''
    Loads the data from the file specified in u_conf and returns the parameters of the
    simulation as (N_conf, N_ion, lattice vectors, list of configurations).
    '''
    # load parser and save nr of ions and lattice vectors
    parser = Parser(u_conf['file_in'])
    lattice_vectors = parser.find_lattice_vectors()
    lat_consts = np.diag(lattice_vectors.dot(lattice_vectors.T))

    # check if lattice constant is bigger than 2 rcut
    if any(np.greater(2 * u_conf["cutoff"], lat_consts)):
        raise ValueError('Cutoff cannot be bigger than half the lattice constants')

    # build the configurations from the parser
    configurations = [
        Configuration(position, energy, force) for (energy, position, force) in parser
        .build_configurations(u_conf['stepsize'], offset)
    ]

    return (len(configurations), parser.find_ion_nr(), lattice_vectors, configurations)


def init_configurations(u_conf: dict, configurations: list, q: np.array, C: np.array) -> None:
    '''
    Initializes the nearest neighbors and descriptors. Writes values into the C array.
    Choosen this way, to only have sideeffects and no return.
    '''
    n_conf = u_conf['N_conf']
    # calculate the nearest neighbors and the descriptors
    t_0 = time()
    for (alpha, config) in enumerate(configurations):
        config.init_nn(u_conf['cutoff'], u_conf['lattice_vectors'])
        config.init_descriptor(q)
        C[alpha, :, :] = config.descriptors
        print(f'calculating NN and descriptors: {alpha+1}/{n_conf}', end='\r')
    print(f'calculating NN and descriptors: finished after {time()-t_0:.3} s')


def build_linear(u_conf: dict, configurations: list, C: np.array, q: np.array) -> (np.array, np.array, np.array, np.array):
    '''
    Intializes the kernel and then builds the linear system with the kernel matrices according to kernel.
    Already normalizes the data to <E> = 0.
    '''
    kern = kernel.Kernel(*u_conf['kernel'])
    n_conf = u_conf['N_conf']
    n_ion = u_conf['N_ion']
    nc_ni = n_conf*n_ion
    # will be the super vectors
    E = np.zeros(n_conf)
    # Holds forces flattened
    F = np.zeros(n_conf * n_ion * 3)
    # The Matrix that is used for fitting the forces
    T = np.zeros((n_conf * n_ion * 3, nc_ni))

    # reshape descriptors
    descr = C.reshape(n_conf * n_ion, len(q))

    t_0 = time()
    print('Building K:', end='\r')
    # das erste Argument ist die aktuelle Konfiguration, das zweite die Referenz-Konfiguration
    K = kern.kernel_mat(descr, descr)
    K = np.sum(
        K.reshape(n_conf, n_ion, nc_ni),
        axis=1
    )
    print(f'Building K: finished after {time()-t_0:.3} s')

    t_0 = time()
    for alpha in range(n_conf):
        print(f'Building [E, F, T]: {alpha+1}/{n_conf}', end='\r')
        E[alpha] = configurations[alpha].energy
        F[alpha*n_ion*3: (alpha+1)*n_ion*3] = configurations[alpha].forces.flatten()
        T[alpha*n_ion*3:(alpha+1)*n_ion*3] = kern.force_submat(q, configurations[alpha], descr)
    print(f'Building [E, F, T]: finished after {time()-t_0:.3} s')

    return (E, F, K, T)

##### ##### Reference: Equation (24) ##### #####
def ridge_regression(K, E, lamb):
    X = np.matmul(np.transpose(K), K)
    y = np.matmul(np.transpose(K), E)
    # (X+lamb*I) * w - y = 0
    N = np.shape(K)[1]
    w = np.linalg.solve(X + lamb * np.eye(N), y)
    return w


def main():
    # load the simulation parameters
    config_path = sys.argv[1] if len(sys.argv) > 1 else 'user_config.json'
    with open(config_path, 'r') as u_conf:
        user_config = json.load(u_conf)

    # make a list of the allowed qs
    qs = np.arange(1, user_config['nr_modi']+1) * pi / user_config['cutoff']

    # read in data and save parameters for calibration comparison
    (user_config['N_conf'], user_config['N_ion'], user_config['lattice_vectors'], configurations) = load_data(user_config)

    # All descriptors in compact super-matrix
    C = np.zeros([user_config['N_conf'], user_config['N_ion'], user_config['nr_modi']])
    # compute the nn and configurations and fill them in C
    init_configurations(user_config, configurations, qs, C)

    # build the linear system
    (E, F, K, T) = build_linear(user_config, configurations, C, qs)

    # centering the energy for (probably) more precise results
    E_ave = np.mean(E)
    E = E - E_ave

    t_0 = time()
    # calculate the weights using ridge regression
    print('Solving linear system ... ', end='\r')
    w = ridge_regression(np.append(K,T, axis=0), np.append(E,F, axis=0), user_config['lambda'])
    print(f'Solving linear system: finished after {time()-t_0:.3} s')

    # make a data directory
    directory = user_config['file_out']
    if not os.path.exists(directory):
        os.makedirs(directory)
    # save calibration (file content will be overwritten if file already exists)
    np.savetxt(directory + '/calibration_w.out', w)
    np.savetxt(directory + '/calibration_C.out', np.reshape(C, (user_config['N_conf'] * user_config['N_ion'], user_config['nr_modi'])))
    np.savetxt(directory + '/calibration_E.out', [E_ave, E_ave])
    # loading: C_cal = np.reshape(np.loadtxt('calibration.out'), (N_conf, N_ion, user_config['nr_modi']))


if __name__ == '__main__':
    main()
