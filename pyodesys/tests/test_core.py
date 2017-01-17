# -*- coding: utf-8 -*-
from __future__ import (absolute_import, division, print_function)

import math
from collections import OrderedDict

import pytest
import numpy as np
from .. import ODESys, OdeSys  # OdeSys deprecated
from ..core import integrate_chained
from ..util import requires


def vdp_f(t, y, p):
    return [y[1], -y[0] + p[0]*y[1]*(1 - y[0]**2)]


def vdp_dfdt(t, y, p):
    return [0, 0]


def vdp_j(t, y, p):
    Jmat = np.zeros((2, 2))
    Jmat[0, 0] = 0
    Jmat[0, 1] = 1
    Jmat[1, 0] = -1 - p[0]*2*y[1]*y[0]
    Jmat[1, 1] = p[0]*(1 - y[0]**2)
    return Jmat


@requires('scipy')
def test_params():
    odes = OdeSys(vdp_f, vdp_j)
    tout, y0, p = [0, 1, 2], [1, 0], [2.0]
    xout, yout, info = odes.integrate(tout, y0, p)
    # blessed values:
    ref = [[1, 0], [0.44449086, -1.32847148], [-1.89021896, -0.71633577]]
    assert np.allclose(yout, ref)
    assert info['nfev'] > 0
    assert info['success']


@requires('scipy', 'pygslodeiv2', 'pycvodes', 'pyodeint')
@pytest.mark.parametrize('integrator', ['scipy', 'gsl', 'cvode', 'odeint'])
def test_adaptive(integrator):
    odes = ODESys(vdp_f, vdp_j, vdp_dfdt)
    kwargs = dict(params=[2.0])
    y0, t0, tend = [1, 0], 0, 2
    xout, yout, info = odes.adaptive(y0, t0, tend, integrator=integrator, **kwargs)
    # something is off with odeint (it looks as it is the step
    # size control which is too optimistic).
    ref = [-1.89021896, -0.71633577]
    assert xout.size > 1
    assert np.allclose(yout[-1, :], ref, rtol=.2 if integrator == 'odeint' else 1e-5)
    assert info['success']
    xout2, yout2, info2 = integrate_chained([odes], {}, [t0, tend], y0, **kwargs)
    assert xout2.size > 1
    assert np.allclose(ref, yout2[-1, :])


@requires('scipy', 'pygslodeiv2', 'pycvodes', 'pyodeint')
@pytest.mark.parametrize('solver', ['scipy', 'gsl', 'odeint', 'cvode'])
def test_predefined(solver):
    odes = ODESys(vdp_f, vdp_j, vdp_dfdt)
    xout = [0, 0.7, 1.3, 2]
    yout, info = odes.predefined([1, 0], xout, params=[2.0], integrator=solver)
    assert np.allclose(yout[-1, :], [-1.89021896, -0.71633577])


@requires('scipy')
def test_pre_post_processors():
    """
    y(x) = A * exp(-k * x)
    dy(x)/dx = -k * A * exp(-k * x) = -k * y(x)

    First transformation:
    v = y/y(x0)
    u = k*x
    ===>
        v(u) = exp(-u)
        dv(u)/du = -v(u)

    Second transformation:
    s = ln(v)
    r = u
    ===>
        s(r) = -r
        ds(r)/dr = -1
    """
    def pre1(x, y, p):
        return x*p[0], y/y[0], [p[0], y[0]]

    def post1(x, y, p):
        return x/p[0], y*p[1], [p[0]]

    def pre2(x, y, p):
        return x, np.log(y), p

    def post2(x, y, p):
        return x, np.exp(y), p

    def dsdr(x, y, p):
        return [-1]

    odesys = ODESys(dsdr, pre_processors=(pre1, pre2),
                    post_processors=(post2, post1))
    k = 3.7
    A = 42
    tend = 7
    xout, yout, info = odesys.integrate(np.asarray([0, tend]), np.asarray([A]),
                                        [k], atol=1e-12, rtol=1e-12,
                                        name='vode', method='adams')
    yref = A*np.exp(-k*xout)
    assert np.allclose(yout.flatten(), yref)
    assert np.allclose(info['internal_yout'].flatten(), -info['internal_xout'])


def test_custom_module():
    from pyodesys.integrators import RK4_example_integartor
    odes = ODESys(vdp_f, vdp_j)
    xout, yout, info = odes.integrate(
        [0, 2], [1, 0], params=[2.0], integrator=RK4_example_integartor,
        first_step=1e-2)
    # blessed values:
    assert np.allclose(yout[0], [1, 0])
    assert np.allclose(yout[-1], [-1.89021896, -0.71633577])
    assert info['nfev'] == 4*2/1e-2

    xout, yout, info = odes.integrate(
        np.linspace(0, 2, 150), [1, 0], params=[2.0],
        integrator=RK4_example_integartor)

    assert np.allclose(yout[0], [1, 0])
    assert np.allclose(yout[-1], [-1.89021896, -0.71633577])
    assert info['nfev'] == 4*149


def decay(t, y, p):
    return [-y[0]*p[0], y[0]*p[0]]


def decay_jac(t, y, p):
    return [[-p[0], 0],
            [p[0], 0]]


def decay_dfdt(t, y, p):
    return [0, 0]


def _test_integrate_multiple_predefined(odes, **kwargs):
    _xout = np.array([[0, 1, 2], [0, 1, 2], [0, 1, 2]])
    _y0 = np.array([[1, 2], [2, 3], [3, 4]])
    _params = np.array([[5], [6], [7]])
    xout, yout, info = odes.integrate(_xout, _y0, params=_params, **kwargs)
    for idx in range(3):
        ref = _y0[idx, 0]*np.exp(-_params[idx, 0]*xout[idx, :])
        assert np.allclose(yout[idx, :, 0], ref)
        assert np.allclose(yout[idx, :, 1], _y0[idx, 0] - ref + _y0[idx, 1])
        assert info[idx]['nfev'] > 0


@requires('scipy')
def test_integarte_multiple_predefined__scipy():
    _test_integrate_multiple_predefined(ODESys(decay), integrator='scipy', method='dopri5')


@requires('pycvodes')
def test_integarte_multiple_predefined__cvode():
    _test_integrate_multiple_predefined(ODESys(decay), integrator='cvode', method='adams', atol=1e-9)


@requires('pyodeint')
def test_integarte_multiple_predefined__odeint():
    _test_integrate_multiple_predefined(ODESys(decay), integrator='odeint', method='bulirsch_stoer', atol=1e-9)


@requires('pygslodeiv2')
def test_integarte_multiple_predefined__gsl():
    _test_integrate_multiple_predefined(ODESys(decay), integrator='gsl', method='rkck')


def sine(t, y, p):
    # x = A*sin(k*t)
    # x' = A*k*cos(k*t)
    # x'' = -A*k**2*sin(k*t)
    k = p[0]
    return [y[1], -k**2 * y[0]]


def sine_jac(t, y, p):
    k = p[0]
    Jmat = np.zeros((2, 2))
    Jmat[0, 0] = 0
    Jmat[0, 1] = 1
    Jmat[1, 0] = -k**2
    Jmat[1, 1] = 0
    return Jmat


def sine_dfdt(t, y, p):
    return [0, 0]


@requires('scipy')
def test_par_by_name():
    odesys = ODESys(sine, sine_jac, param_names=['k'], par_by_name=True)
    A, k = 2, 3
    xout, yout, info = odesys.integrate(np.linspace(0, 1), [0, A*k], {'k': k})
    assert info['success']
    assert xout.size > 7
    ref = [
        A*np.sin(k*(xout - xout[0])),
        A*np.cos(k*(xout - xout[0]))*k
    ]
    assert np.allclose(yout[:, 0], ref[0], atol=1e-5, rtol=1e-5)
    assert np.allclose(yout[:, 1], ref[1], atol=1e-5, rtol=1e-5)


@requires('scipy')
def test_dep_by_name():
    odesys = ODESys(sine, sine_jac, names=['prim', 'bis'], dep_by_name=True)
    A, k = 2, 3
    for y0 in ({'prim': 0, 'bis': A*k}, [0, A*k]):
        xout, yout, info = odesys.integrate(np.linspace(0, 1), y0, [k])
        assert info['success']
        assert xout.size > 7
        ref = [
            A*np.sin(k*(xout - xout[0])),
            A*np.cos(k*(xout - xout[0]))*k
        ]
        assert np.allclose(yout[:, 0], ref[0], atol=1e-5, rtol=1e-5)
        assert np.allclose(yout[:, 1], ref[1], atol=1e-5, rtol=1e-5)


def _test_integrate_multiple_adaptive(odes, **kwargs):
    _xout = np.array([[0, 1], [1, 2], [1, 7]])
    Ak = [[2, 3], [3, 4], [4, 5]]
    _y0 = [[0., A*k] for A, k in Ak]
    _params = [[k] for A, k in Ak]

    def _ref(A, k, t):
        return [A*np.sin(k*(t - t[0])), A*np.cos(k*(t - t[0]))*k]

    xout, yout, info = odes.integrate(_xout, _y0, _params, **kwargs)
    for idx in range(3):
        ref = _ref(Ak[idx][0], Ak[idx][1], xout[idx])
        assert np.allclose(yout[idx][:, 0], ref[0], atol=1e-5, rtol=1e-5)
        assert np.allclose(yout[idx][:, 1], ref[1], atol=1e-5, rtol=1e-5)
        assert info[idx]['nfev'] > 0


@requires('scipy')
def test_integarte_multiple_adaptive__scipy():
    _test_integrate_multiple_adaptive(ODESys(sine, sine_jac),
                                      integrator='scipy', method='bdf', name='vode', first_step=1e-9)


@requires('pycvodes')
def test_integarte_multiple_adaptive__pycvodes():
    _test_integrate_multiple_adaptive(ODESys(sine, sine_jac),
                                      integrator='cvode', method='bdf', nsteps=700)


@requires('pyodeint')
def test_integarte_multiple_adaptive__pyodeint():
    _test_integrate_multiple_adaptive(ODESys(sine, sine_jac, sine_dfdt),
                                      integrator='odeint', method='rosenbrock4', nsteps=1000)


@requires('pygslodeiv2')
def test_integarte_multiple_adaptive__pygslodeiv2():
    _test_integrate_multiple_adaptive(ODESys(sine, sine_jac, sine_dfdt),
                                      integrator='gsl', method='bsimp')


def decay_factory(ny):

    def f(t, y, p):
        return [(y[i-1]*p[i-1] if i > 0 else 0) - (y[i]*p[i] if i < ny else 0) for i in range(ny)]

    def j(t, y, p):
        return [
            [(p[ci] if ci == ri - 1 else 0) - (p[ci] if ci == ri else 0) for ci in range(ny)]
            for ri in range(ny)
        ]

    def dfdt(t, y, p):
        return [0]*ny

    return f, j, dfdt


@requires('pyodeint', 'scipy')
def test_par_by_name__multi():
    from scipy.special import binom
    for ny in range(6, 8):
        p_max = 3
        a = 0.42  # > 0
        params = OrderedDict([
            (chr(ord('a')+idx), [
                (idx + 1 + p)*math.log(a + 1) for p in range(p_max + 1)
            ]) for idx in range(ny)
        ])
        ref = np.array([[binom(p + idx, p)*(a/(a+1))**idx/(a+1)**(p+1) for idx in range(ny)]
                        for p in range(p_max + 1)])
        odesys = ODESys(*decay_factory(ny), param_names=params.keys(), par_by_name=True)
        result = odesys.integrate(np.linspace(0, 1), [1] + [0]*(ny-1), params,
                                  integrator='odeint', method='rosenbrock4')
        assert all(nfo['success'] for nfo in result.info)
        assert result.xout.shape[-1] == 50
        assert np.allclose(result.yout[:, -1, :], ref)


@requires('pygslodeiv2')
def test_par_by_name__multi__single_varied():
    ny = 3
    odesys1 = ODESys(*decay_factory(ny), param_names='a b c'.split(), par_by_name=True)
    params1 = {'a': 2, 'b': (3, 4, 5, 6, 7), 'c': 0}
    init1 = [42, 0, 0]
    result1 = odesys1.integrate(2.1, init1, params1, integrator='gsl')
    for idx1 in range(len(params1['b'])):
        ref_a1 = init1[0]*np.exp(-params1['a']*result1.xout[idx1])
        ref_b1 = init1[0]*params1['a']*(
            np.exp(-params1['a']*result1.xout[idx1]) -
            np.exp(-params1['b'][idx1]*result1.xout[idx1]))/(params1['b'][idx1] - params1['a'])
        ref_c1 = init1[0] - ref_a1 - ref_b1
        assert np.allclose(result1.yout[idx1][:, 0], ref_a1)
        assert np.allclose(result1.yout[idx1][:, 1], ref_b1)
        assert np.allclose(result1.yout[idx1][:, 2], ref_c1)

    odesys2 = ODESys(*decay_factory(ny), names='a b c'.split(), dep_by_name=True)
    init2 = {'a': (7, 13, 19, 23, 42, 101), 'b': 0, 'c': 0}
    params2 = [11.7, 12.3, 0]
    result2 = odesys2.integrate(3.4, init2, params2, integrator='gsl')
    for idx2 in range(len(init2['a'])):
        ref_a2 = init2['a'][idx2]*np.exp(-params2[0]*result2.xout[idx2])
        ref_b2 = init2['a'][idx2]*params2[0]*(
            np.exp(-params2[0]*result2.xout[idx2]) -
            np.exp(-params2[1]*result2.xout[idx2]))/(params2[1] - params2[0])
        ref_c2 = init2['a'][idx2] - ref_a2 - ref_b2
        assert np.allclose(result2.yout[idx2][:, 0], ref_a2)
        assert np.allclose(result2.yout[idx2][:, 1], ref_b2)
        assert np.allclose(result2.yout[idx2][:, 2], ref_c2)


@requires('scipy')
def test_zero_time_adaptive():
    odes = ODESys(sine, sine_jac)
    xout, yout, info = odes.integrate(0, [0, 1], [2])
    assert xout.shape == (1,)
    assert yout.shape == (1, 2)


def _test_first_step_cb(integrator, atol=1e-8, rtol=1e-8, forgive=10):
    odesys = ODESys(decay, decay_jac, decay_dfdt, first_step_cb=lambda x, y, p, backend=None: y[0]*1e-30)
    _y0 = [.7, 0]
    k = [1e23]
    xout, yout, info = odesys.integrate(5, _y0, k, integrator=integrator, atol=atol, rtol=rtol)
    ref = _y0[0]*np.exp(-k[0]*xout[:])
    assert np.allclose(yout[:, 0], ref, atol=atol*forgive, rtol=rtol*forgive)
    assert np.allclose(yout[:, 1], _y0[0] - ref + _y0[1], atol=atol*forgive, rtol=rtol*forgive)
    assert info['nfev'] > 0


@requires('pycvodes')
def test_first_step_cb__cvode():
    _test_first_step_cb('cvode')


@requires('pygslodeiv2')
def test_first_step_cb__gsl():
    _test_first_step_cb('gsl')


@requires('pyodeint')
def test_first_step_cb__odeint():
    _test_first_step_cb('odeint')


@requires('pycvodes')
def test_roots():
    def f(t, y):
        return [y[0]]

    def roots(t, y, p=(), backend=np):
        return [y[0] - backend.exp(1)]

    kwargs = dict(dx0=1e-12, atol=1e-12, rtol=1e-12,
                  integrator='cvode', method='adams', return_on_root=True)
    odesys = ODESys(f, roots_cb=roots, nroots=1)
    xout, yout, info = odesys.integrate(2, [1], **kwargs)
    assert len(info['root_indices']) == 1
    assert np.min(np.abs(xout - 1)) < 1e-11
