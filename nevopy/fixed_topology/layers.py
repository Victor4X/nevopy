# MIT License
#
# Copyright (c) 2020 Gabriel Nogueira (Talendar)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# ==============================================================================

""" Implements neural network layers.

This module implements a variety of neural network layers to be used by genomes
in the context of neuroevolution.
"""

from abc import ABC, abstractmethod
from typing import Any, Tuple, Dict, List

from nevopy.base_genome import InvalidInputError
from nevopy.fixed_topology.config import FixedTopologyConfig
import numpy as np

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = "1"
import tensorflow as tf


class BaseLayer(ABC):
    """ Abstract base class that defines a neural network layer.

    This abstract base class defines the general structure and behaviour of a
    neural network layer in the context of neuroevolutionary algorithms.

    Args:
        config (FixedTopologyConfig): Settings being used in the current
            evolutionary session.

    Attributes:
        config (FixedTopologyConfig): Settings being used in the current
            evolutionary session.
    """

    def __init__(self, config: FixedTopologyConfig):
        self.config = config

    @property
    @abstractmethod
    def weights(self) -> Tuple[Any, Any]:
        """ A tuple with the layer's weights and biases.

        Usually contained within a `NumPy ndarray` or a `TensorFlow tensor`.
        """

    @abstractmethod
    def process(self, X: Any) -> Any:
        """ Feeds the given input(s) to the layer.

        This is where the layer's logic lives.

        Args:
            X (Any): The input(s) to be fed to the layer. Usually a
                `NumPy ndarray` or a `TensorFlow tensor`.

        Returns:
            The output of the layer. Usually a `NumPy ndarray` or a
            `TensorFlow tensor`.

        Raises:
            InvalidInputError: If the shape of ``X`` doesn't match the input
                shape expected by the layer.
        """

    def __call__(self, X: Any) -> Any:
        """ Wraps a call to :meth:`.process`. """
        return self.process(X)

    @abstractmethod
    def deep_copy(self) -> "BaseLayer":
        """ Makes an exact/deep copy of the layer.

        Returns:
            An exact/deep copy of the layer.
        """

    @abstractmethod
    def mutate_weights(self) -> None:
        """ Randomly mutates the weights of the layer's connections. """

    @abstractmethod
    def mate(self, other: Any) -> "BaseLayer":
        """ Mates two layers to produce a new layer (offspring).

        Implements the sexual reproduction between a pair of layers. The new
        layer inherits information from both parents (not necessarily in an
        equal proportion)

        Args:
            other (Any): The second layer . If it's not compatible for mating
                with the current layer (`self`), an exception will be raised.

        Returns:
            A new layer (the offspring born from the sexual reproduction between
            the current layer and the layer passed as argument.

        Raises:
            IncompatibleLayersError: If the layer passed as argument to
                ``other`` is incompatible with the current layer (`self`).
        """


class TensorFlowLayer(BaseLayer, ABC):
    """ Abstract base class for layers that wrap a `TensorFlow` layer.

    When subclassing this class, be sure to call ``super().__ init __()``
    passing, as named arguments, the same arguments received by the subclass's
    `` __init__()``. These arguments will be stored in the instance variable
    ``self._num_layer_kwargs``;

    This is necessary because this class implements :meth:`.deep_copy()`. This
    method is implemented in the base class because it performs, in general, the
    same actions regardless of the internal details of each subclass.

    You'll usually do something like this:

        .. code-block:: python

            class MyTFLayer(TensorFlowLayer):
                def __init__(self, arg1, arg2, **kwargs):
                    super().__init__(**{k: v for k, v in locals().items()
                                        if k != "self"})
                    # ...

    Args:
        config (FixedTopologyConfig): Settings being used in the current
            evolutionary session.
        **kwargs: Named arguments to be passed to the constructor of a subclass
            of this base class when making a copy of the subclass.
    """

    def __init__(self, config: FixedTopologyConfig, **kwargs):
        super().__init__(config)
        self._new_layer_kwargs = kwargs

    @property
    @abstractmethod
    def tf_layer(self) -> tf.keras.layers.Layer:
        """
        The `tf.keras.layers.Layer
        <https://www.tensorflow.org/api_docs/python/tf/keras/layers/Layer>`_
        used internally.
        """

    @property
    def weights(self) -> Tuple[tf.Tensor, tf.Tensor]:
        """ The current weights and biases of the layer.

        Wrapper for :py:meth:`tf.keras.layers.Layer.weights`.

        The weights of a layer represent the state of the layer. This property
        returns the weight values associated with this layer as a list of Numpy
        arrays. In most cases, it's a list containing the weights of the layer's
        connections and the bias values (one for each neuron, generally).
        """
        return self.tf_layer.weights

    @weights.setter
    def weights(self, new_weights: Tuple[Any, Any]) -> None:
        """ Wrapper for :py:`tf.keras.layers.Layer.set_weights()`. """
        self.tf_layer.set_weights(new_weights)

    def process(self, X: Any) -> tf.Tensor:
        try:
            return self.tf_layer(X)
        except ValueError as e:
            raise InvalidInputError("The given input's shape doesn't match the "
                                    "shape expected by the layer! "
                                    f"TensorFlow's error message: {str(e)}")

    def deep_copy(self) -> "BaseLayer":
        new_layer = self.__class__(**self._new_layer_kwargs)
        new_layer.weights = self.weights
        return new_layer

    def mutate_weights(self, _test_info=None) -> None:
        """ Randomly mutates the weights of the layer's connections.

        Each weight will be perturbed by an amount defined in the settings of
        the current evolutionary session. Each weight also has a chance of being
        reset (a new random value is assigned to it).
        """
        weights, bias = self.weights

        # weight perturbation
        w_perturbation = tf.random.uniform(
            shape=weights.shape,
            minval=1 - self.config.weight_perturbation_pc,
            maxval=1 + self.config.weight_perturbation_pc,
        )
        weights = tf.math.multiply(weights, w_perturbation).numpy()

        # weight reset
        num_w_reset = np.random.binomial(weights.size,
                                         self.config.weight_reset_chance)
        if num_w_reset > 0:
            w_reset_idx = np.random.randint(0, weights.size, size=num_w_reset)
            weights.flat[w_reset_idx] = np.random.uniform(
                low=self.config.new_weight_interval[0],
                high=self.config.new_weight_interval[1],
                size=num_w_reset,
            )

        # bias perturbation
        b_perturbation = tf.random.uniform(
            shape=bias.shape,
            minval=1 - self.config.bias_perturbation_pc,
            maxval=1 + self.config.bias_perturbation_pc,
        )
        bias = tf.math.multiply(bias, b_perturbation).numpy()

        # bias reset
        num_b_reset = np.random.binomial(bias.size,
                                         self.config.bias_reset_chance)
        if num_b_reset > 0:
            b_reset_idx = np.random.randint(0, bias.size,
                                            size=num_b_reset)
            bias.flat[b_reset_idx] = np.random.uniform(
                low=self.config.new_bias_interval[0],
                high=self.config.new_bias_interval[1],
                size=num_b_reset,
            )

        # setting new weights and biases
        self.weights = (weights, bias)

        # test info
        if _test_info is not None:
            _test_info["w_perturbation"] = w_perturbation
            _test_info["b_perturbation"] = b_perturbation
            # noinspection PyUnboundLocalVariable
            _test_info["w_reset_idx"] = w_reset_idx if num_w_reset > 0 else []
            # noinspection PyUnboundLocalVariable
            _test_info["b_reset_idx"] = b_reset_idx if num_b_reset > 0 else []


class TFConv2DLayer(TensorFlowLayer):
    """ Wraps a `TensorFlow` 2D convolution layer.

    This is a wrapper for `tf.keras.layers.Conv2D
    <https://www.tensorflow.org/api_docs/python/tf/keras/layers/Conv2D>`_.

    Args:
        config (FixedTopologyConfig): Settings being used in the current
            evolutionary session.
        **kwargs: Named arguments to be passed to the constructor of the
            TensorFlow layer.
    """

    def __init__(self,
                 filters: int,
                 kernel_size: Tuple[int, int],
                 config: FixedTopologyConfig,
                 strides: Tuple[int, int] = (1, 1),
                 padding: str = "valid",
                 activation="relu",
                 **kwargs: Dict[str, Any]) -> None:
        super().__init__(**{k: v for k, v in locals().items() if k != "self"})
        self._tf_layer = tf.keras.layers.Conv2D(filters=filters,
                                                kernel_size=kernel_size,
                                                strides=strides,
                                                padding=padding,
                                                activation=activation,
                                                **kwargs)

    @property
    def tf_layer(self) -> tf.keras.layers.Conv2D:
        return self._tf_layer

    def mate(self, other: "TFConv2DLayer") -> "TFConv2DLayer":
        """ TODO

        TODO: chance of inheriting a filter from one of the parents

        Args:
            other:

        Returns:

        """
        pass


class IncompatibleLayersError(Exception):
    """
    Indicates that an attempt has been made to mate (sexual reproduction) two
    incompatible layers.
    """