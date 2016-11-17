from SimPEG import Mesh, Maps, Utils, Tests
from SimPEG.EM import FDEM
import numpy as np
from scipy.constants import mu_0

import unittest

MuMax = 200.
TOL = 1e-10
EPS = 1e-20

np.random.seed(101)


def setupMeshModel():
    cs = 10.
    nc = 20.
    npad = 15.
    hx = [(cs, nc), (cs, npad, 1.3)]
    hz = [(cs, npad, -1.3), (cs, nc), (cs, npad, 1.3)]

    mesh = Mesh.CylMesh([hx, 1., hz], '0CC')
    muMod = MuMax*np.random.rand(mesh.nC)
    sigmaMod = np.random.randn(mesh.nC)

    return mesh, muMod, sigmaMod


def setupProblem(
    mesh, muMod, sigmaMod, prbtype='e', sigmaInInversion=False, freq=1.
):
    rxcomp = ['real', 'imag']

    loc = Utils.ndgrid(
        [mesh.vectorCCx, np.r_[0.], mesh.vectorCCz]
    )

    if prbtype in ['e', 'b']:
        rxfields_y = ['j'] #, 'j']
        rxfields_xz = [] #['b', 'h']

    elif prbtype in ['h', 'j']:
        rxfields_y = [] # ['b', 'h']
        rxfields_xz = ['e'] #['e', 'j']

    rxList_edge = [
        getattr(FDEM.Rx, 'Point_{f}'.format(f=f))(
            loc, component=comp, orientation=orient
        )
        for f in rxfields_y
        for comp in rxcomp
        for orient in ['y']
    ]

    rxList_face = [
        getattr(FDEM.Rx, 'Point_{f}'.format(f=f))(
            loc, component=comp, orientation=orient
        )
        for f in rxfields_xz
        for comp in rxcomp
        for orient in ['x', 'z']
    ]

    rxList = rxList_edge + rxList_face

    src_loc = np.r_[0., 0., 0.]

    if prbtype in ['e', 'b']:
        src = FDEM.Src.MagDipole(
            rxList=rxList, loc=src_loc, freq=freq
        )

    elif prbtype in ['h', 'j']:
        ind = Utils.closestPoints(mesh, src_loc, 'Fz') + mesh.vnF[0]
        vec = np.zeros(mesh.nF)
        vec[ind] = 1.

        src = FDEM.Src.RawVec_e(rxList=rxList, freq=freq, s_e=vec)

    survey = FDEM.Survey([src])

    if sigmaInInversion:
        m0 = np.hstack([muMod, sigmaMod])

        wires = Maps.Wires(
            ('mu', mesh.nC),
            ('sigma', mesh.nC)
        )

        muMap = Maps.ChiMap(mesh) * wires.mu
        sigmaMap = Maps.ExpMap(mesh) * wires.sigma

        prob = getattr(FDEM, 'Problem3D_{}'.format(prbtype))(
            mesh, muMap=muMap, sigmaMap=sigmaMap
        )

    else:
        m0 = muMod
        prob = getattr(FDEM, 'Problem3D_{}'.format(prbtype))(
                mesh, sigma=sigmaMod, muMap=Maps.ChiMap(mesh)
            )

    prob.pair(survey)

    return m0, prob, survey


class MuTests(unittest.TestCase):

    def setUpProb(self, prbtype='e', sigmaInInversion=False):
        self.mesh, muMod, sigmaMod = setupMeshModel()
        self.m0, self.prob, self.survey = setupProblem(
            self.mesh, muMod, sigmaMod, prbtype=prbtype,
            sigmaInInversion=sigmaInInversion
        )

    def JvecTest(self, prbtype='e', sigmaInInversion=False):
        self.setUpProb(prbtype, sigmaInInversion)
        print('Testing Jvec {}'.format(prbtype))

        def fun(x):
            return (
                self.prob.survey.dpred(x), lambda x: self.prob.Jvec(self.m0, x)
            )
        return Tests.checkDerivative(
            fun, self.m0, num=2, plotIt=False, eps=EPS
        )

    def JtvecTest(self, prbtype='e', sigmaInInversion=False):
        self.setUpProb(prbtype, sigmaInInversion)
        print('Testing Jvec {}'.format(prbtype))

        m = np.random.rand(self.prob.muMap.nP)
        v = np.random.rand(self.survey.nD)

        self.prob.model = self.m0

        V1 = v.dot(self.prob.Jvec(self.m0, m))
        V2 = m.dot(self.prob.Jtvec(self.m0, v))
        diff = np.abs(V1-V2)
        tol = TOL * (np.abs(V1) + np.abs(V2))/2.
        passed = diff < tol
        print(
            'AdjointTest {prbtype} {v1} {v2} {diff} {tol} {passed}'.format(
                prbtype=prbtype, v1=V1, v2=V2, diff=diff, tol=tol,
                passed=passed
            )
        )
        return passed


    def test_Jvec_e(self):
        self.assertTrue(self.JvecTest('e', sigmaInInversion=False))

    def test_Jvec_b(self):
        self.assertTrue(self.JvecTest('b', sigmaInInversion=False))

    def test_Jvec_j(self):
        self.assertTrue(self.JvecTest('j', sigmaInInversion=False))

    def test_Jvec_h(self):
        self.assertTrue(self.JvecTest('h', sigmaInInversion=False))

    def test_Jtvec_e(self):
        self.assertTrue(self.JtvecTest('e', sigmaInInversion=False))

    def test_Jtvec_b(self):
        self.assertTrue(self.JtvecTest('b', sigmaInInversion=False))

    def test_Jtvec_j(self):
        self.assertTrue(self.JtvecTest('j', sigmaInInversion=False))

    def test_Jtvec_h(self):
        self.assertTrue(self.JtvecTest('h', sigmaInInversion=False))

    def test_Jvec_musig_e(self):
        self.assertTrue(self.JvecTest('e', sigmaInInversion=True))

    def test_Jvec_musig_b(self):
        self.assertTrue(self.JvecTest('b', sigmaInInversion=True))

    def test_Jvec_musig_j(self):
        self.assertTrue(self.JvecTest('j', sigmaInInversion=True))

    def test_Jvec_musig_h(self):
        self.assertTrue(self.JvecTest('h', sigmaInInversion=True))

    def test_Jtvec_musig_e(self):
        self.assertTrue(self.JtvecTest('e', sigmaInInversion=True))

    def test_Jtvec_musig_b(self):
        self.assertTrue(self.JtvecTest('b', sigmaInInversion=True))

    def test_Jtvec_musig_j(self):
        self.assertTrue(self.JtvecTest('j', sigmaInInversion=True))

    def test_Jtvec_musig_h(self):
        self.assertTrue(self.JtvecTest('h', sigmaInInversion=True))

if __name__ == '__main__':
    unittest.main()


