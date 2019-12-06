import properties
import numpy as np
from ... import survey


class point_receiver(survey.BaseRx):
    """
    Gravity point receiver class for integral formulation

    :param numpy.ndarray locations: receiver locations index (ie. :code:`np.c_[ind_1, ind_2, ...]`)
    :param string component: receiver component
         "gx", "gy", "gz", "gxx", "gxy", "gxz",
         "gyy", "gyz", "gzz", "guv", "amp" [default]
    """

    # receiver_index = None

    # component = properties.List(
    #     "Must be a magnetic component of the type",


    #     default=["gz"]
    # )

    def __init__(self, locations, components="gz", **kwargs):

        n_locations = locations.shape[0]

        if isinstance(components, str):
            components = [components]

        component_dict = {}
        for component in components:
            component_dict[component] = np.ones(n_locations, dtype='bool')

        assert np.all([component in [
            "gx", "gy", "gz", "gxx", "gxy", "gxz",
            "gyy", "gyz", "gzz", "guv"
             ] for component in list(component_dict.keys())]), (
                "Components {0!s} not known. Components must be in "
                "'gx', 'gy', 'gz', 'gxx', 'gxy', 'gxz'"
         	    "'gyy', 'gyz', 'gzz', 'guv'"
                "Arbitrary orientations have not yet been "
                "implemented.".format(component)
            )
        self.components = component_dict

        super(survey.BaseRx, self).__init__(locations=locations, components=components, **kwargs)

    def nD(self):

        if self.receiver_index is not None:

            return self.location_index.shape[0]

        elif self.locations is not None:

            return self.locations.shape[0]

        else:

            return None

    def receiver_index(self):

        return self.receiver_index
