from math import exp
import numpy as np
import configuration

def linear_kernel(descriptor1: np.array, descriptor2: np.array) -> float:
    if np.shape(descriptor1) != np.shape(descriptor2):
        raise ValueError('Shapes of input do not match')

    return np.inner(descriptor1, descriptor2)

def gaussian_kernel(descriptor1: np.array, descriptor2: np.array, sigma: float) -> float:
    if np.shape(descriptor1) != np.shape(descriptor2):
        raise ValueError('Shapes of input do not match')

    return exp(np.linalg.norm(descriptor1 - descriptor2)**2 / (2 * sigma**2))


class Kernel:
    def __init__(self, mode, **kwargs):
        if mode == 'linear':
            self.kernel = linear_kernel
        elif mode == 'gaussian':
            if 'sigma' not in kwargs:
                raise ValueError('For the Gaussian Kernel a sigma has to be supplied')
            self.kernel = lambda x, y: gaussian_kernel(x, y, kwargs['sigma'])
        else: 
            raise ValueError(f'kernel {mode} is not supported')

