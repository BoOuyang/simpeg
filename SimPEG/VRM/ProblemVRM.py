from SimPEG import Problem, mkvc, Maps, Props, Solver as simpegSolver
from SimPEG.VRM.SurveyVRM import SurveyVRM
# from SimPEG.VRM.FieldsVRM import Fields_Linear
import numpy as np
import scipy.sparse as sp
import discretize

############################################
# BASE VRM PROBLEM CLASS
############################################


class BaseProblemVRM(Problem.BaseProblem):
    """
Base class for VRM problem.

REQUIRED ARGUMENTS:

mesh: 3D tensor or OcTree mesh

KWARGS:

refFact: Maximum refinement factor for sensitivities (default = 3)
refRadius: Distances from source in which cell sensitivities are refined.
           Must be an array or list with elements equal to the refFact.
           (default based on minimum cell size)
indActive: A numpy array with boolean entries, where the True entries
           refer to topography cell which will be computed in the
           forward model (default is all mesh cells)

    """

    # SET CLASS ATTRIBUTES
    _refFact = None
    _refRadius = None
    _indActive = None
    _AisSet = False

    surveyPair = SurveyVRM

    def __init__(self, mesh, **kwargs):

        # **kwargs
        self._refFact = kwargs.get('refFact', 3)
        self._refRadius = kwargs.get('refRadius', 1.25*np.mean(np.r_[np.min(mesh.h[0]), np.min(mesh.h[1]), np.min(mesh.h[2])])*np.arange(1, self.refFact+1))
        self._indActive = kwargs.get('indActive', np.ones(mesh.nC, dtype=bool))

        # Assertions
        assert len(mesh.h) == 3, 'Problem requires 3D tensor or OcTree mesh'
        assert isinstance(self._refFact, int), "Refinement factor must be set as an integer"
        assert len(self._refRadius) >= self._refFact, 'Number of refinement radii must equal or greater than refinement factor'
        assert list(self._indActive).count(True) + list(self._indActive).count(False) == len(self._indActive), "indActive must be a boolean array"

        if self.refFact > 4:
            print("Refinement factor larger than 4 may result in computations which exceed memory limits")

        super(BaseProblemVRM, self).__init__(mesh, **kwargs)

    @property
    def refFact(self):
        return self._refFact

    @refFact.setter
    def refFact(self, Val):

        assert isinstance(Val, int) and Val > -1, "Refinement factor must be an integer value equal or larger than 0"

        if Val != len(self._refRadius):
            print("Refinement factor no longer matches length of refinement radii array. Please ensure refinement factor is equal or less to number of elements in refinement radii")

        if Val > 4:
            print("Refinement factor larger than 4 may result in computations which exceed memory limits")

        self._refFact = Val

    @property
    def refRadius(self):
        return self._refRadius

    @refRadius.setter
    def refRadius(self, Array):
        assert isinstance(Array, np.ndarray), "Array must be a numpy array"

        if self._refFact != len(Array):
            print("Refinement factor no longer matches length of refinement radii array. Please ensure that the number of elements in refinement radii is equal or greater than the refinement factor")

        self._refRadius = Array

    @property
    def indActive(self):
        return self._indActive

    @indActive.setter
    def indActive(self, Vec):

        assert list(self._indActive).count(True) + list(self._indActive).count(False) == len(self._indActive), "indActive must be a boolean array"
        self._AisSet = False
        self._indActive = Vec

    def _getH0matrix(self, xyz, pp):

        """
Creates sparse matrix containing inducing field components for source pp

INPUTS:

xyz: N X 3 array of locations to predict field
pp: Source index
        """

        SrcObj = self.survey.srcList[pp]

        H0 = SrcObj.getH0(xyz)

        Hx0 = sp.diags(H0[:, 0], format="csr")
        Hy0 = sp.diags(H0[:, 1], format="csr")
        Hz0 = sp.diags(H0[:, 2], format="csr")

        H0 = sp.vstack([Hx0, Hy0, Hz0])

        return H0

    def _getGeometryMatrix(self, xyzc, xyzh, pp):

        """
Creates the dense geometry matrix mapping from magentized voxel cells to the
receivers for source pp

INPUTS:

xyzc: N by 3 array containing cell center locations
xyzh: N by 3 array containing cell dimensions
pp: Source index
        """

        srcObj = self.survey.srcList[pp]

        N = np.shape(xyzc)[0]   # Number of cells
        K = srcObj.nRx          # Number of receiver in all rxList

        ax = np.reshape(xyzc[:, 0] - xyzh[:, 0]/2, (1, N))
        bx = np.reshape(xyzc[:, 0] + xyzh[:, 0]/2, (1, N))
        ay = np.reshape(xyzc[:, 1] - xyzh[:, 1]/2, (1, N))
        by = np.reshape(xyzc[:, 1] + xyzh[:, 1]/2, (1, N))
        az = np.reshape(xyzc[:, 2] - xyzh[:, 2]/2, (1, N))
        bz = np.reshape(xyzc[:, 2] + xyzh[:, 2]/2, (1, N))

        G = np.zeros((K, 3*N))
        C = -(1/(4*np.pi))
        eps = 1e-10

        COUNT = 0

        for qq in range(0, len(srcObj.rxList)):

            rxObj = srcObj.rxList[qq]
            dComp = rxObj.fieldComp
            locs = rxObj.locs
            M = np.shape(locs)[0]

            if dComp is 'x':
                for rr in range(0, M):
                    u1 = locs[rr, 0] - ax
                    u1[np.abs(u1) < 1e-10] = np.min(xyzh[:, 0])/1000
                    u2 = locs[rr, 0] - bx
                    u2[np.abs(u2) < 1e-10] = -np.min(xyzh[:, 0])/1000
                    v1 = locs[rr, 1] - ay
                    v1[np.abs(v1) < 1e-10] = np.min(xyzh[:, 1])/1000
                    v2 = locs[rr, 1] - by
                    v2[np.abs(v2) < 1e-10] = -np.min(xyzh[:, 1])/1000
                    w1 = locs[rr, 2] - az
                    w1[np.abs(w1) < 1e-10] = np.min(xyzh[:, 2])/1000
                    w2 = locs[rr, 2] - bz
                    w2[np.abs(w2) < 1e-10] = -np.min(xyzh[:, 2])/1000

                    Gxx = (
                        np.arctan((v1*w1)/(u1*np.sqrt(u1**2+v1**2+w1**2)+eps)) -
                        np.arctan((v1*w1)/(u2*np.sqrt(u2**2+v1**2+w1**2)+eps)) +
                        np.arctan((v2*w1)/(u2*np.sqrt(u2**2+v2**2+w1**2)+eps)) -
                        np.arctan((v2*w1)/(u1*np.sqrt(u1**2+v2**2+w1**2)+eps)) +
                        np.arctan((v2*w2)/(u1*np.sqrt(u1**2+v2**2+w2**2)+eps)) -
                        np.arctan((v1*w2)/(u1*np.sqrt(u1**2+v1**2+w2**2)+eps)) +
                        np.arctan((v1*w2)/(u2*np.sqrt(u2**2+v1**2+w2**2)+eps)) -
                        np.arctan((v2*w2)/(u2*np.sqrt(u2**2+v2**2+w2**2)+eps))
                    )

                    Gyx = (
                        np.log(np.sqrt(u1**2+v1**2+w1**2)-w1) -
                        np.log(np.sqrt(u2**2+v1**2+w1**2)-w1) +
                        np.log(np.sqrt(u2**2+v2**2+w1**2)-w1) -
                        np.log(np.sqrt(u1**2+v2**2+w1**2)-w1) +
                        np.log(np.sqrt(u1**2+v2**2+w2**2)-w2) -
                        np.log(np.sqrt(u1**2+v1**2+w2**2)-w2) +
                        np.log(np.sqrt(u2**2+v1**2+w2**2)-w2) -
                        np.log(np.sqrt(u2**2+v2**2+w2**2)-w2)
                    )

                    Gzx = (
                        np.log(np.sqrt(u1**2+v1**2+w1**2)-v1) -
                        np.log(np.sqrt(u2**2+v1**2+w1**2)-v1) +
                        np.log(np.sqrt(u2**2+v2**2+w1**2)-v2) -
                        np.log(np.sqrt(u1**2+v2**2+w1**2)-v2) +
                        np.log(np.sqrt(u1**2+v2**2+w2**2)-v2) -
                        np.log(np.sqrt(u1**2+v1**2+w2**2)-v1) +
                        np.log(np.sqrt(u2**2+v1**2+w2**2)-v1) -
                        np.log(np.sqrt(u2**2+v2**2+w2**2)-v2)
                    )

                    G[COUNT, :] = C*np.c_[Gxx, Gyx, Gzx]
                    COUNT = COUNT + 1

            elif dComp is 'y':
                for rr in range(0, M):
                    u1 = locs[rr, 0] - ax
                    u1[np.abs(u1) < 1e-10] = np.min(xyzh[:, 0])/1000
                    u2 = locs[rr, 0] - bx
                    u2[np.abs(u2) < 1e-10] = -np.min(xyzh[:, 0])/1000
                    v1 = locs[rr, 1] - ay
                    v1[np.abs(v1) < 1e-10] = np.min(xyzh[:, 1])/1000
                    v2 = locs[rr, 1] - by
                    v2[np.abs(v2) < 1e-10] = -np.min(xyzh[:, 1])/1000
                    w1 = locs[rr, 2] - az
                    w1[np.abs(w1) < 1e-10] = np.min(xyzh[:, 2])/1000
                    w2 = locs[rr, 2] - bz
                    w2[np.abs(w2) < 1e-10] = -np.min(xyzh[:, 2])/1000

                    Gxy = (
                        np.log(np.sqrt(u1**2+v1**2+w1**2)-w1) -
                        np.log(np.sqrt(u2**2+v1**2+w1**2)-w1) +
                        np.log(np.sqrt(u2**2+v2**2+w1**2)-w1) -
                        np.log(np.sqrt(u1**2+v2**2+w1**2)-w1) +
                        np.log(np.sqrt(u1**2+v2**2+w2**2)-w2) -
                        np.log(np.sqrt(u1**2+v1**2+w2**2)-w2) +
                        np.log(np.sqrt(u2**2+v1**2+w2**2)-w2) -
                        np.log(np.sqrt(u2**2+v2**2+w2**2)-w2)
                    )

                    Gyy = (
                        np.arctan((u1*w1)/(v1*np.sqrt(u1**2+v1**2+w1**2)+eps)) -
                        np.arctan((u2*w1)/(v1*np.sqrt(u2**2+v1**2+w1**2)+eps)) +
                        np.arctan((u2*w1)/(v2*np.sqrt(u2**2+v2**2+w1**2)+eps)) -
                        np.arctan((u1*w1)/(v2*np.sqrt(u1**2+v2**2+w1**2)+eps)) +
                        np.arctan((u1*w2)/(v2*np.sqrt(u1**2+v2**2+w2**2)+eps)) -
                        np.arctan((u1*w2)/(v1*np.sqrt(u1**2+v1**2+w2**2)+eps)) +
                        np.arctan((u2*w2)/(v1*np.sqrt(u2**2+v1**2+w2**2)+eps)) -
                        np.arctan((u2*w2)/(v2*np.sqrt(u2**2+v2**2+w2**2)+eps))
                    )

                    Gzy = (
                        np.log(np.sqrt(u1**2+v1**2+w1**2)-u1) -
                        np.log(np.sqrt(u2**2+v1**2+w1**2)-u2) +
                        np.log(np.sqrt(u2**2+v2**2+w1**2)-u2) -
                        np.log(np.sqrt(u1**2+v2**2+w1**2)-u1) +
                        np.log(np.sqrt(u1**2+v2**2+w2**2)-u1) -
                        np.log(np.sqrt(u1**2+v1**2+w2**2)-u1) +
                        np.log(np.sqrt(u2**2+v1**2+w2**2)-u2) -
                        np.log(np.sqrt(u2**2+v2**2+w2**2)-u2)
                    )

                    G[COUNT, :] = C*np.c_[Gxy, Gyy, Gzy]
                    COUNT = COUNT + 1

            elif dComp is 'z':
                for rr in range(0, M):
                    u1 = locs[rr, 0] - ax
                    u1[np.abs(u1) < 1e-10] = np.min(xyzh[:, 0])/1000
                    u2 = locs[rr, 0] - bx
                    u2[np.abs(u2) < 1e-10] = -np.min(xyzh[:, 0])/1000
                    v1 = locs[rr, 1] - ay
                    v1[np.abs(v1) < 1e-10] = np.min(xyzh[:, 1])/1000
                    v2 = locs[rr, 1] - by
                    v2[np.abs(v2) < 1e-10] = -np.min(xyzh[:, 1])/1000
                    w1 = locs[rr, 2] - az
                    w1[np.abs(w1) < 1e-10] = np.min(xyzh[:, 2])/1000
                    w2 = locs[rr, 2] - bz
                    w2[np.abs(w2) < 1e-10] = -np.min(xyzh[:, 2])/1000

                    Gxz = (
                        np.log(np.sqrt(u1**2+v1**2+w1**2)-v1) -
                        np.log(np.sqrt(u2**2+v1**2+w1**2)-v1) +
                        np.log(np.sqrt(u2**2+v2**2+w1**2)-v2) -
                        np.log(np.sqrt(u1**2+v2**2+w1**2)-v2) +
                        np.log(np.sqrt(u1**2+v2**2+w2**2)-v2) -
                        np.log(np.sqrt(u1**2+v1**2+w2**2)-v1) +
                        np.log(np.sqrt(u2**2+v1**2+w2**2)-v1) -
                        np.log(np.sqrt(u2**2+v2**2+w2**2)-v2)
                    )

                    Gyz = (
                        np.log(np.sqrt(u1**2+v1**2+w1**2)-u1) -
                        np.log(np.sqrt(u2**2+v1**2+w1**2)-u2) +
                        np.log(np.sqrt(u2**2+v2**2+w1**2)-u2) -
                        np.log(np.sqrt(u1**2+v2**2+w1**2)-u1) +
                        np.log(np.sqrt(u1**2+v2**2+w2**2)-u1) -
                        np.log(np.sqrt(u1**2+v1**2+w2**2)-u1) +
                        np.log(np.sqrt(u2**2+v1**2+w2**2)-u2) -
                        np.log(np.sqrt(u2**2+v2**2+w2**2)-u2)
                    )

                    Gzz = (
                        - np.arctan((v1*w1)/(u1*np.sqrt(u1**2+v1**2+w1**2)+eps)) +
                        np.arctan((v1*w1)/(u2*np.sqrt(u2**2+v1**2+w1**2)+eps)) -
                        np.arctan((v2*w1)/(u2*np.sqrt(u2**2+v2**2+w1**2)+eps)) +
                        np.arctan((v2*w1)/(u1*np.sqrt(u1**2+v2**2+w1**2)+eps)) -
                        np.arctan((v2*w2)/(u1*np.sqrt(u1**2+v2**2+w2**2)+eps)) +
                        np.arctan((v1*w2)/(u1*np.sqrt(u1**2+v1**2+w2**2)+eps)) -
                        np.arctan((v1*w2)/(u2*np.sqrt(u2**2+v1**2+w2**2)+eps)) +
                        np.arctan((v2*w2)/(u2*np.sqrt(u2**2+v2**2+w2**2)+eps))
                    )

                    Gzz = (
                        Gzz -
                        np.arctan((u1*w1)/(v1*np.sqrt(u1**2+v1**2+w1**2)+eps)) +
                        np.arctan((u2*w1)/(v1*np.sqrt(u2**2+v1**2+w1**2)+eps)) -
                        np.arctan((u2*w1)/(v2*np.sqrt(u2**2+v2**2+w1**2)+eps)) +
                        np.arctan((u1*w1)/(v2*np.sqrt(u1**2+v2**2+w1**2)+eps)) -
                        np.arctan((u1*w2)/(v2*np.sqrt(u1**2+v2**2+w2**2)+eps)) +
                        np.arctan((u1*w2)/(v1*np.sqrt(u1**2+v1**2+w2**2)+eps)) -
                        np.arctan((u2*w2)/(v1*np.sqrt(u2**2+v1**2+w2**2)+eps)) +
                        np.arctan((u2*w2)/(v2*np.sqrt(u2**2+v2**2+w2**2)+eps))
                    )

                    G[COUNT, :] = C*np.c_[Gxz, Gyz, Gzz]
                    COUNT = COUNT + 1

        return np.matrix(G)

    def _getAMatricies(self):

        indActive = self.indActive

        # GET CELL INFORMATION FOR FORWARD MODELING
        meshObj = self.mesh
        xyzc = meshObj.gridCC[indActive, :]
        xyzh = meshObj.gridH[indActive, :]

        # GET LIST OF A MATRICIES
        A = []
        for pp in range(0, self.survey.nSrc):

            # Create initial A matrix
            G = self._getGeometryMatrix(xyzc, xyzh, pp)
            H0 = self._getH0matrix(xyzc, pp)
            A.append(G*H0)

            # Refine A matrix
            refFact = self.refFact
            refRadius = self.refRadius

            if refFact > 0:

                srcObj = self.survey.srcList[pp]
                refFlag = srcObj._getRefineFlags(xyzc, refFact, refRadius)

                for qq in range(1, refFact+1):

                    A[pp][:, refFlag == qq] = self._getSubsetAcolumns(xyzc, xyzh, pp, qq, refFlag)

        return A

    def _getSubsetAcolumns(self, xyzc, xyzh, pp, qq, refFlag):

        """
This method returns the refined sensitivities for columns that will be replaced
in the A matrix for source pp and refinement factor qq.

INPUTS:

    xyzc: Cell centers of topo mesh cells N X 3 array
    xyzh: Cell widths of topo mesh cells N X 3 array
    pp: Source ID
    qq: Mesh refinement factor
    refFlag: refinement factors for all topo mesh cells
        """

        # GET SUBMESH GRID
        n = 2**qq
        [nx, ny, nz] = np.meshgrid(np.linspace(1, n, n)-0.5, np.linspace(1, n, n)-0.5, np.linspace(1, n, n)-0.5)
        nxyz_sub = np.c_[mkvc(nx), mkvc(ny), mkvc(nz)]

        xyzh_sub = xyzh[refFlag == qq, :]     # Get widths of cells to be refined
        xyzc_sub = xyzc[refFlag == qq, :] - xyzh[refFlag == qq, :]/2   # Get bottom southwest corners of cells to be refined
        m = np.shape(xyzc_sub)[0]
        xyzc_sub = np.kron(xyzc_sub, np.ones((n**3, 1)))     # Kron for n**3 refined cells
        xyzh_sub = np.kron(xyzh_sub/n, np.ones((n**3, 1)))   # Kron for n**3 refined cells with widths h/n
        nxyz_sub = np.kron(np.ones((m, 1)), nxyz_sub)        # Kron for n**3 refined cells
        xyzc_sub = xyzc_sub + xyzh_sub*nxyz_sub

        # GET SUBMESH A MATRIX AND COLLAPSE TO COLUMNS
        G = self._getGeometryMatrix(xyzc_sub, xyzh_sub, pp)
        H0 = self._getH0matrix(xyzc_sub, pp)
        Acols = (G*H0)*sp.kron(sp.diags(np.ones(m)), np.ones((n**3, 1)))

        return Acols


#############################################################################
# VRM CHARACTERISTIC DECAY FORMULATION (SINGLE MODEL PARAMETER AND INVERSION)
#############################################################################


class LinearVRM(BaseProblemVRM):

    """
Problem class for linear VRM problem. The the solution to this problem
is a time-approximate solution which uses the characteristic decay of
the VRM response. The solution is only capable of providing the VRM
response during the off-time. For background theory, see Cowan (2016).

REQUIRED ARGUMENTS:

    mesh: 3D tensor or OcTree mesh

KWARGS:

refFact: Maximum refinement factor for sensitivities (default = 3)
refRadius: Distances from source in which cell sensitivities are refined.
           Must be an array or list with elements equal to the refFact.
            (default based on minimum cell size)
indActive: A numpy array with boolean entries, where the True entries
           refer to topography cell which will be computed in the
           forward model (default is all mesh cells)

xiMap: A SimPEG mapping object which maps the model to the active
       topography cells (i.e. indActive)

    """

    _A = None
    _T = None
    _TisSet = False
    _xiMap = None

    xi, xiMap, xiDeriv = Props.Invertible("Amalgamated Viscous Remanent Magnetization Parameter xi = dchi/ln(tau2/tau1)")

    def __init__(self, mesh, **kwargs):

        super(LinearVRM, self).__init__(mesh, **kwargs)

        nAct = list(self._indActive).count(True)
        self._xiMap = kwargs.get('xiMap', Maps.IdentityMap(nP=nAct))

    @property
    def xiMap(self):
        return self._xiMap

    @xiMap.setter
    def xiMap(self, mappingObj):
        # Assert Statement???
        self._AisSet = False
        self._xiMap = mappingObj

    @property
    def A(self):

        """
This function constructs the geometric sensitivity matrix for the linear VRM
problem. This function requires that the problem be paired with a survey
object.
        """

        if self._AisSet is False:

            assert self.ispaired, "Problem must be paired with survey to generate A matrix"

            # Remove any previously stored A matrix
            if self._A is not None:
                self._A = None

            print('CREATING A MATRIX')

            # COLLAPSE ALL A MATRICIES INTO SINGLE OPERATOR
            self._A = np.vstack(self._getAMatricies())
            self._AisSet = True

            return self._A

        elif self._AisSet is True:

            return self._A

    @property
    def T(self):

        """
This function returns the characteristic decay matrix. This function requires
that the problem has been paired with a survey object.

fType: The field type (h, dh/dt, b, db/dt) that will be computed. If fType is
       None, then the field type is computed according to the receivers.
        """

        if self._TisSet is False:

            assert self.ispaired, "Problem must be paired with survey to generate T matrix"

            # Remove any previously stored T matrix
            if self._T is not None:
                self._T = None

            print('CREATING T MATRIX')

            srcList = self.survey.srcList
            nSrc = len(srcList)
            T = []

            for pp in range(0, nSrc):

                rxList = srcList[pp].rxList
                nRx = len(rxList)
                waveObj = srcList[pp].waveform

                for qq in range(0, nRx):

                    times = rxList[qq].times
                    nLoc = np.shape(rxList[qq].locs)[0]

                    I = sp.diags(np.ones(nLoc))
                    eta = waveObj.getCharDecay(rxList[qq].fieldType, times)
                    eta = np.matrix(eta).T

                    T.append(sp.kron(I, eta))

            self._T = sp.block_diag(T)
            self._TisSet = True

            return self._T

        elif self._TisSet is True:

            return self._T

    def fields(self, m):

        assert self.ispaired, "Problem must be paired with survey to predict data"

        # Project to active mesh cells
        m = np.matrix(self.xiMap * m).T

        # Must return as an array
        return np.array(sp.coo_matrix.dot(self.T, self.A*m))

    def Jvec(self, m, v, f=None):

        """Compute Pd*T*A*Pt'*Pm*v"""

        assert self.ispaired, "Problem must be paired with survey to predict data"

        v = np.matrix(mkvc(v)).T

        # Project to active mesh cells
        v = sp.csr_matrix.dot(self.xiMap.P, v)

        # Multiply by A
        v = self.A*v

        # Get active time rows of T
        T = self.T.tocsr()[self.survey.tActive, :]

        # Must return an array
        return np.array(sp.csr_matrix.dot(T, v))

    def Jtvec(self, m, v, f=None):

        """Compute Pm'*Pt*A'*T'*Pd'*v"""

        assert self.ispaired, "Problem must be paired with survey to predict data"

        # Get v'
        v = np.matrix(mkvc(v))

        # Get T'*v
        T = self.T.tocsr()[self.survey.tActive, :]
        v = sp.csc_matrix.dot(T.transpose(), v.T)

        # Get A'*T'*v
        v = np.dot(v.T, self.A).T

        # Project to full active mesh cells
        v = sp.csc_matrix.dot(self.xiMap.P.T, v)

        # Must return an array
        return np.array(v)

    def unpair(self):
        """Unbind a survey from this problem instance."""
        if not self.ispaired:
            return
        self.survey._prob = None
        self._survey = None
        self._A = None
        self._T = None
        self._AisSet = False
        self._TisSet = False


class LogUniformVRM(BaseProblemVRM):

    """
Problem class for VRM assuming a log-normal distribution of time-relaxation
constants. This model for VRM requires 4 model parameters for each cell:
chi0, dchi, tau1, tau2.

REQUIRED ARGUMENTS:

mesh: 3D tensor or OcTree mesh

KWARGS:

refFact: Maximum refinement factor for sensitivities (default = 3)
refRadius: Distances from source in which cell sensitivities are refined.
           Must be an array or list with elements equal to the refFact.
            (default based on minimum cell size)
indActive: A numpy array with boolean entries, where the True entries
           refer to topography cell which will be computed in the
           forward model (default is all mesh cells)

xiMap: A SimPEG mapping object which maps the model to the active
       topography cells (i.e. indActive)

    """

    _A = None
    _T = None
    _TisSet = False
    _xiMap = None

    xi, xiMap, xiDeriv = Props.Invertible("Amalgamated Viscous Remanent Magnetization Parameter xi = dchi/ln(tau2/tau1)")

    def __init__(self, mesh, **kwargs):

        super(LogUniformVRM, self).__init__(mesh, **kwargs)

        nAct = list(self._indActive).count(True)
        self._xiMap = kwargs.get('xiMap', Maps.IdentityMap(nP=nAct))

    @property
    def xiMap(self):
        return self._xiMap

    @xiMap.setter
    def xiMap(self, mappingObj):
        # Assert Statement???
        self._AisSet = False
        self._xiMap = mappingObj

    @property
    def A(self):

        """
This function constructs the geometric sensitivity matrix for the VRM
problem. This function requires that the problem be paired with a survey
object.
        """

        if self._AisSet is False:

            assert self.ispaired, "Problem must be paired with survey to generate A matrix"

            # Remove any previously stored A matrix
            if self._A is not None:
                self._A = None

            print('CREATING A MATRIX')

            # COLLAPSE ALL A MATRICIES INTO SINGLE OPERATOR
            self._A = self._getAMatricies()
            self._AisSet = True

            return self._A

        elif self._AisSet is True:

            return self._A

    def fields(self, m_chi0, m_dchi, m_tau1, m_tau2):

        assert self.ispaired, "Problem must be paired with survey to predict data"

        # Extract viscosity parameters
        chi0 = self.xiMap*m_chi0
        dchi = self.xiMap*m_dchi
        tau1 = self.xiMap*m_tau1
        tau2 = self.xiMap*m_tau2

        # Fields from each source
        srcList = self.survey.srcList
        nSrc = len(srcList)
        f = []

        for pp in range(0, nSrc):

            rxList = srcList[pp].rxList
            nRx = len(rxList)
            waveObj = srcList[pp].waveform

            for qq in range(0, nRx):

                times = rxList[qq].times
                eta = waveObj.getLogUniformDecay(rxList[qq].fieldType, times, chi0, dchi, tau1, tau2)

                f.append(mkvc((self.A[qq] * np.matrix(eta)).T))

        return np.array(np.hstack(f))






















