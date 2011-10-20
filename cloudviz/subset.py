import numpy as np
import pyfits

import cloudviz
from cloudviz.exceptions import IncompatibleDataException
from cloudviz.visual import VisualAttributes

class Subset(object):
    """Base class to handle subsets of data.

    These objects both describe subsets of a dataset, and relay any
    state changes to the hub that their parent data are assigned to.

    This base class only directly impements the logic that relays
    state changes back to the hub. Subclasses implement the actual
    description and manipulation of data subsets

    Attributes:
    -----------
    data : data instance
        The dataset that this subset describes
    style : VisualAttributes instance
        Describes visual attributes of the subset
    """

    class ListenDict(dict):
        """
        A small dictionary class to keep track of visual subset
        properties. Updates are broadcasted through the subset

        """
        def __init__(self, subset):
            dict.__init__(self)
            self._subset = subset

        def __setitem__(self, key, value):
            dict.__setitem__(self, key, value)
            self._subset.broadcast(self)

    def __init__(self, data, color='r', alpha=1.0, label=None):
        """ Create a new subclass object.

        """
        self.data = data
        self._broadcasting = False
        self.style = VisualAttributes()
        self.label = label

    def register(self):
        """ Register a subset to its data, and start broadcasting
        state changes

        """
        self.data.add_subset(self)
        self.do_broadcast(True)

    def to_index_list(self, data=None):
        """
        Convert the current subset to a list of indices. These index
        the elements in the data object that belong to the subset.

        This method must be overridden by subclasses

        Parameters:
        -----------
        data: Data instance
              If this is provided, return an index list for the
              elements in this data set (if possible). Otherwise,
              return an index list for the data associated with this
              subset (if any)

        Returns:
        --------

        A numpy array, giving the indices of elements in the data that
        belong to this subset.

        Raises:
        -------
        IncompatibleDataException: if an index list cannot be created
        for the requested data set.

        """
        raise NotImplementedError("must be overridden by a subclass")

    def to_mask(self, data=None):
        """
        Convert the current subset to a mask.

        Parameters:
        -----------
        data: Data instance
              If this is provided, return a mask for the
              elements in this data set (if possible). Otherwise,
              return a mask list for the data associated with this
              subset (if any)

        Returns:
        --------

        A boolean numpy array, the same shape as the data, that
        defines whether each element belongs to the subset.
        """
        raise NotImplementedError("must be overridden by a subclass")

    def do_broadcast(self, value):
        """
        Set whether state changes to the subset are relayed to a hub.

        It can be useful to turn off broadcasting, when modifying the
        subset in ways that don't impact any of the clients.

        Attributes:
        value: Whether the subset should broadcast state changes (True/False)

        """
        object.__setattr__(self, '_broadcasting', value)

    def broadcast(self, attribute=None):
        """
        Explicitly broadcast a SubsetUpdateMessage to the hub

        Note that in most situations, broadcasting happens
        automatically.

        Parameters:
        -----------
        attribute: string
                   The name of the attribute (if any) that should be
                   broadcast as updated.
        """

        try:
            if self._broadcasting and self.data.hub:
                msg = cloudviz.message.SubsetUpdateMessage(self,
                                                           attribute=attribute)
                self.data.hub.broadcast(msg)
        except (AttributeError):
            pass

    def unregister(self):
        """Broadcast a SubsetDeleteMessage to the hub, and stop braodcasting"""

        try:
            if self._broadcasting and self.data.hub:
                msg = cloudviz.message.SubsetDeleteMessage(self)
                self.data.hub.broadcast(msg)
        except (AttributeError):
            pass
        self._broadcasting = False

    def write_mask(self, file_name, format="fits"):
        """ Write a subset mask out to file
        
        Inputs:
        -------
        file_name: String
                   name of file to write to
        format: String
                Name of format to write to. Currently, only "fits" is
                supported
                
        """

        mask = np.short(self.to_mask())
        if format == 'fits':
            pyfits.writeto(file_name, mask, clobber=True)
        else:
            raise AttributeError("format not supported: %s" % format)
                    

    def __del__(self):
        self.unregister()

    def __setattr__(self, attribute, value):
        object.__setattr__(self, attribute, value)
        self.broadcast(attribute)

    def _check_compatibility(self, other):
        if not isinstance(other, Subset):
            raise TypeError("Incompatible types: %s vs %s" %
                            (type(self), type(other)))
        if self.data is not other.data:
            raise TypeError("Subsets describe different data")

    def __or__(self, other):
        self._check_compatibility(self, other)
        m = self.to_mask() | other.to_mask()
        return ElementSubset(self.data, mask=m)

    def __and__(self, other):
        self._check_compatibility(self, other)
        m = self.to_mask() & other.to_mask()
        return ElementSubset(self.data, mask=m)

    def __xor__(self, other):
        self._check_compatibility(self, other)
        m = self.to_mask() ^ other.to_mask()
        return ElementSubset(self.data, mask=m)

    def is_compatible(self, data):
        """
        Return whether or not this subset is compatible with a data
        set.  If a subset and data set are compatible, then
        subset.to_mask(data=data) and subset.to_index_map(data=data)
        should return appropriate values.

        Parameters:
        -----------
        data: data instance
        the data set to check for compatibility

        Returns:
        --------
        True if the data is compatible with this subset. Else false
        """
        return data is self.data


class TreeSubset(Subset):
    """ Subsets defined using a data's Tree attribute.

    The tree attribute in a data set defines a hierarchical
    partitioning of the data. This subset class represents subsets
    that consist of portions of this tree (i.e., a subset of the nodes
    in the tree)

    Attributes:
    -----------
    node_list: A list of integers, specifying which nodes in the tree
               belong to the subset.

    """
    def __init__(self, data, node_list=None):
        """ Create a new subset instance

        Parameters:
        -----------
        data: A data instance
              The data must have a tree attribute with a populated index_map

        node_list: List
                  A list of node ids, defining which parts of the data's tree
                  belong to this subset.
        """
        if not hasattr(data, 'tree'):
            raise AttributeError("Input data must contain a tree object")

        if data.tree.index_map is None:
            raise AttributeError("Input data's tree must have an index map")

        Subset.__init__(self, data)
        if not node_list:
            self.node_list = []
        else:
            self.node_list = node_list

    def to_mask(self, data=None):

        if data is not None and data is not self.data:
            raise IncompatibleDataException("TreeSubsets cannot cross "
                                            "data sets")

        t = self.data.tree
        im = t.index_map
        mask = np.zeros(self.data.shape, dtype=bool)
        for n in self.node_list:
            mask |= im == n
        return mask

    def to_index_list(self, data=None):

        if data is not None and data is not self.data:
            raise IncompatibleDataException("TreeSubsets cannot cross"
                                            " data sets")

        # this is inefficient for small subsets.
        return self.to_mask().nonzero()[0]

    def __or__(self, other):
        self.check_compatibility(other)
        if isinstance(other, TreeSubset):
            nl = list(set(self.node_list) | set(other.node_list))
            return TreeSubset(self.data, node_list=nl)
        else:
            return Subset.__or__(self, other)

    def __and__(self, other):
        self.check_compatibility(other)
        if isinstance(other, TreeSubset):
            nl = list(set(self.node_list) & set(other.node_list))
            return TreeSubset(self.data, node_list=nl)
        else:
            return Subset.__and__(self, other)

    def __xor__(self, other):
        self.check_compatibility(other)
        if isinstance(other, TreeSubset):
            nl = list(set(self.node_list) ^ set(other.node_list))
            return TreeSubset(self.data, node_list=nl)
        else:
            return Subset.__xor__(self, other)

    def __ior__(self, other):
        self.check_compatibility(other)
        if isinstance(other, TreeSubset):
            nl = list(set(self.node_list) | set(other.node_list))
            self.node_list = nl
            return self
        else:
            return Subset.__ior__(self, other)

    def __iand__(self, other):
        self.check_compatibility(other)
        if isinstance(other, TreeSubset):
            nl = list(set(self.node_list) & set(other.node_list))
            self.node_list = nl
            return self
        else:
            return Subset.__iand__(self, other)

    def __ixor__(self, other):
        self.check_compatibility(other)
        if isinstance(other, TreeSubset):
            nl = list(set(self.node_list) ^ set(other.node_list))
            self.node_list = nl
            return self
        else:
            return Subset.__ixor__(self, other)


class ElementSubset(Subset):
    """
    This is a simple subset object that explicitly defines
    which elements of the data set are included in the subset

    Attributes:
    -----------

    mask: A boolean numpy array, the same shape as the data.
          The true/false value determines whether each element
          belongs to the subset.
    """

    def __init__(self, data, mask=None):
        """
        Create a new subset object.

        Parameters:
        -----------
        data: class:`cloudviz.data.Data` instance.
              The data to attach this subset to

        mask: Numpy array
              The mask attribute for this subset
        """
        if not mask:
            self.mask = np.zeros(data.shape, dtype=bool)
        else:
            self.mask = mask
        Subset.__init__(self, data)

    def to_mask(self, data=None):

        if data is not None and data is not self.data:
            raise IncompatibleDataException("Element subsets cannot "
                                            "cross data sets")

        return self.mask

    def to_index_list(self, data=None):

        if data is not None and data is not self.data:
            raise IncompatibleDataException("Element subsets cannot "
                                            "cross data sets")
        return self.mask.nonzero()[0]

    def __setattr__(self, attribute, value):
        if hasattr(self, 'mask') and attribute == 'mask':
            if value.shape != self.data.shape:
                raise Exception("Mask has wrong shape")
        Subset.__setattr__(self, attribute, value)


class RoiSubset(Subset):
    """ This subset is defined by a class:`cloudviz.roi.Roi` object,
    interpreted using a data set's coordinate object.

    Attributes:
    -----------
    roi: A class:`cloudviz.roi.Roi` instance
         The roi that describes the subset boundaries.
    """

    def __init__(self, data):
        """ Create a new subset 
        
        Parameters:
        -----------
        data: a class:`cloudviz.data.Data` instance
              Which data set to attach this subset to.
        """
        Subset.__init__(self, data)
        self.roi = None
    
    def to_mask(self):
        if self.roi is None or not self.roi.defined():
            return np.zeros_like(self.data, 'bool')

        ind = np.arange(np.product(self.data.shape))
        ind.shape = self.data.shape
        x = ind % self.data.shape[0]
        y = (ind / self.data.shape[0]) % self.data.shape[1]
        xx, yy = self.data.coordinates.pixel2world(self, x, y)
        
        return self.roi.contains(xx, yy)

        
