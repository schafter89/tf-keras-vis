import numpy as np
import pytest
import tensorflow as tf
from packaging.version import parse as version
from tensorflow.keras.models import load_model

from tf_keras_vis.saliency import Saliency
from tf_keras_vis.utils.scores import BinaryScore, CategoricalScore
from tf_keras_vis.utils.test import (NO_ERROR, assert_error, dummy_sample, mock_conv_model,
                                     mock_conv_model_with_float32_output, mock_multiple_io_model,
                                     score_with_list, score_with_tuple)

if version(tf.version.VERSION) >= version("2.4.0"):
    from tensorflow.keras.mixed_precision import set_global_policy


class TestSaliency():
    @pytest.mark.parametrize("scores,expected_error", [
        (None, ValueError),
        (CategoricalScore(0), NO_ERROR),
        (score_with_tuple, NO_ERROR),
        (score_with_list, NO_ERROR),
        ([None], ValueError),
        ([CategoricalScore(0)], NO_ERROR),
        ([score_with_tuple], NO_ERROR),
        ([score_with_list], NO_ERROR),
    ])
    def test__call__if_score_is_(self, scores, expected_error, conv_model):
        saliency = Saliency(conv_model)
        with assert_error(expected_error):
            result = saliency(scores, dummy_sample((1, 8, 8, 3)))
            assert result.shape == (1, 8, 8)

    @pytest.mark.parametrize("seed_input,expected,expected_error", [
        (None, None, ValueError),
        (dummy_sample((8, )), None, ValueError),
        (dummy_sample((8, 8, 3)), (1, 8, 8), NO_ERROR),
        ([dummy_sample((8, 8, 3))], [(1, 8, 8)], NO_ERROR),
        (dummy_sample((1, 8, 8, 3)), (1, 8, 8), NO_ERROR),
        ([dummy_sample((1, 8, 8, 3))], [(1, 8, 8)], NO_ERROR),
    ])
    def test__call__if_seed_input_is_(self, seed_input, expected, expected_error, conv_model):
        saliency = Saliency(conv_model)
        with assert_error(expected_error):
            result = saliency(CategoricalScore(0), seed_input)
            if type(expected) is list:
                assert type(result) is list
                expected = expected[0]
                result = result[0]
            assert result.shape == expected

    @pytest.mark.parametrize("keepdims,expected", [
        (False, (1, 8, 8)),
        (True, (1, 8, 8, 3)),
    ])
    def test__call__if_keepdims_is_(self, keepdims, expected, conv_model):
        saliency = Saliency(conv_model)
        result = saliency(CategoricalScore(0), dummy_sample((1, 8, 8, 3)), keepdims=keepdims)
        assert result.shape == expected

    @pytest.mark.parametrize("smooth_samples", [1, 3, 100])
    def test__call__if_smoothing_is_active(self, smooth_samples, conv_model):
        saliency = Saliency(conv_model)
        result = saliency(CategoricalScore(0),
                          dummy_sample((1, 8, 8, 3)),
                          smooth_samples=smooth_samples)
        assert result.shape == (1, 8, 8)

    def test__call__if_model_has_only_dense_layers(self, dense_model):
        saliency = Saliency(dense_model)
        result = saliency(CategoricalScore(0), dummy_sample((8, )), keepdims=True)
        assert result.shape == (1, 8)

    @pytest.mark.parametrize("score_class", [BinaryScore, CategoricalScore])
    @pytest.mark.parametrize("modifier_enabled", [False, True])
    @pytest.mark.parametrize("clone_enabled", [False, True])
    @pytest.mark.parametrize("batch_size", [0, 1, 5])
    def test__call__with_categorical_score(self, score_class, modifier_enabled, clone_enabled,
                                           batch_size, conv_model, conv_sigmoid_model):
        # Release v.0.6.0@dev(May 22 2021):
        #   Add this case to test Saliency with ScoreClasses.
        def model_modifier(model):
            model.layers[-1].activation = tf.keras.activations.linear

        if score_class is BinaryScore:
            model = conv_sigmoid_model
        else:
            model = conv_model

        score_targets = np.random.randint(0, 1, max(batch_size, 1))
        score = score_class(list(score_targets))

        seed_input_shape = (8, 8, 3)
        if batch_size > 0:
            seed_input_shape = (batch_size, ) + seed_input_shape
        seed_input = dummy_sample(seed_input_shape)

        saliency = Saliency(model,
                            model_modifier=model_modifier if modifier_enabled else None,
                            clone=clone_enabled)
        result = saliency(score, seed_input=seed_input)
        if modifier_enabled and clone_enabled:
            assert model is not saliency.model
        else:
            assert model is saliency.model
        assert result.shape == (max(batch_size, 1), 8, 8)


class TestSaliencyWithMultipleInputsModel():
    @pytest.mark.parametrize("scores,expected_error", [
        (None, ValueError),
        (CategoricalScore(0), NO_ERROR),
        (score_with_tuple, NO_ERROR),
        (score_with_list, NO_ERROR),
        ([CategoricalScore(0)], NO_ERROR),
    ])
    def test__call__if_score_is_(self, scores, expected_error, multiple_inputs_model):
        saliency = Saliency(multiple_inputs_model)
        with assert_error(expected_error):
            result = saliency(scores, [dummy_sample((1, 8, 8, 3)), dummy_sample((1, 10, 10, 3))])
            assert len(result) == 2
            assert result[0].shape == (1, 8, 8)
            assert result[1].shape == (1, 10, 10)

    @pytest.mark.parametrize("seed_input,expected_error", [
        (None, ValueError),
        (dummy_sample((1, 8, 8, 3)), ValueError),
        ([dummy_sample((1, 8, 8, 3))], ValueError),
        ([dummy_sample((1, 8, 8, 3)), dummy_sample((1, 10, 10, 3))], NO_ERROR),
    ])
    def test__call__if_seed_input_is_(self, seed_input, expected_error, multiple_inputs_model):
        saliency = Saliency(multiple_inputs_model)
        with assert_error(expected_error):
            result = saliency(CategoricalScore(0), seed_input)
            assert len(result) == 2
            assert result[0].shape == (1, 8, 8)
            assert result[1].shape == (1, 10, 10)

    @pytest.mark.parametrize("keepdims,expected", [
        (False, [(1, 8, 8), (1, 10, 10)]),
        (True, [(1, 8, 8, 3), (1, 10, 10, 3)]),
    ])
    def test__call__if_keepdims_is_(self, keepdims, expected, multiple_inputs_model):
        saliency = Saliency(multiple_inputs_model)
        result = saliency(
            CategoricalScore(0), [dummy_sample(
                (1, 8, 8, 3)), dummy_sample((1, 10, 10, 3))],
            keepdims=keepdims)
        assert len(result) == 2
        assert result[0].shape == expected[0]
        assert result[1].shape == expected[1]

    @pytest.mark.parametrize("smooth_samples", [1, 3, 100])
    def test__call__if_smoothing_is_active(self, smooth_samples, multiple_inputs_model):
        saliency = Saliency(multiple_inputs_model)
        result = saliency(
            CategoricalScore(0), [dummy_sample(
                (1, 8, 8, 3)), dummy_sample((1, 10, 10, 3))],
            smooth_samples=smooth_samples)
        assert len(result) == 2
        assert result[0].shape == (1, 8, 8)
        assert result[1].shape == (1, 10, 10)


class TestSaliencyWithMultipleOutputsModel():
    @pytest.mark.parametrize("scores,expected_error", [
        (None, ValueError),
        ([None], ValueError),
        (CategoricalScore(0), ValueError),
        ([CategoricalScore(0)], ValueError),
        ([CategoricalScore(0), None], ValueError),
        ([CategoricalScore(0), CategoricalScore(0)], NO_ERROR),
        ([score_with_tuple, score_with_tuple], NO_ERROR),
        ([score_with_list, score_with_list], NO_ERROR),
    ])
    def test__call__if_score_is_(self, scores, expected_error, multiple_outputs_model):
        saliency = Saliency(multiple_outputs_model)
        with assert_error(expected_error):
            result = saliency(scores, dummy_sample((1, 8, 8, 3)))
            assert result.shape == (1, 8, 8)

    @pytest.mark.parametrize("seed_input,expected,expected_error", [
        (None, None, ValueError),
        (dummy_sample((8, )), None, ValueError),
        (dummy_sample((8, 8, 3)), (1, 8, 8), NO_ERROR),
        ([dummy_sample((8, 8, 3))], [(1, 8, 8)], NO_ERROR),
        (dummy_sample((1, 8, 8, 3)), (1, 8, 8), NO_ERROR),
        ([dummy_sample((1, 8, 8, 3))], [(1, 8, 8)], NO_ERROR),
    ])
    def test__call__if_seed_input_is_(self, seed_input, expected, expected_error,
                                      multiple_outputs_model):
        saliency = Saliency(multiple_outputs_model)
        with assert_error(expected_error):
            result = saliency([CategoricalScore(0), CategoricalScore(0)], seed_input)
            if type(expected) is list:
                assert type(result) is list
                expected = expected[0]
                result = result[0]
            assert result.shape == expected


class TestSaliencyWithMultipleIOModel():
    @pytest.mark.parametrize("scores,expected_error", [
        (None, ValueError),
        ([None], ValueError),
        (CategoricalScore(0), ValueError),
        ([CategoricalScore(0)], ValueError),
        ([CategoricalScore(0), None], ValueError),
        ([CategoricalScore(0), CategoricalScore(0)], NO_ERROR),
        ([score_with_tuple, score_with_tuple], NO_ERROR),
        ([score_with_list, score_with_list], NO_ERROR),
    ])
    def test__call__if_score_is_(self, scores, expected_error, multiple_io_model):
        saliency = Saliency(multiple_io_model)
        with assert_error(expected_error):
            result = saliency(scores, [dummy_sample((1, 8, 8, 3)), dummy_sample((1, 10, 10, 3))])
            assert len(result) == 2
            assert result[0].shape == (1, 8, 8)
            assert result[1].shape == (1, 10, 10)

    @pytest.mark.parametrize("seed_input,expected_error", [
        (None, ValueError),
        (dummy_sample((1, 8, 8, 3)), ValueError),
        ([dummy_sample((1, 8, 8, 3))], ValueError),
        ([dummy_sample((1, 8, 8, 3)), dummy_sample((1, 10, 10, 3))], NO_ERROR),
    ])
    def test__call__if_seed_input_is_(self, seed_input, expected_error, multiple_io_model):
        saliency = Saliency(multiple_io_model)
        with assert_error(expected_error):
            result = saliency([CategoricalScore(0), CategoricalScore(0)], seed_input)
            assert len(result) == 2
            assert result[0].shape == (1, 8, 8)
            assert result[1].shape == (1, 10, 10)


@pytest.mark.skipif(version(tf.version.VERSION) < version("2.4.0"),
                    reason="This test is enabled only when tensorflow version is 2.4.0+.")
class TestSaliencyOnMixedPrecision(TestSaliency):
    @classmethod
    def setup_class(cls):
        tf.keras.mixed_precision.set_global_policy('mixed_float16')

    @classmethod
    def teardown_class(cls):
        tf.keras.mixed_precision.set_global_policy('float32')


@pytest.mark.skipif(version(tf.version.VERSION) < version("2.4.0"),
                    reason="This test is enabled only when tensorflow version is 2.4.0+.")
class TestSaliencyWithMultipleInputsModelOnMixedPrecision(TestSaliencyWithMultipleInputsModel):
    @classmethod
    def setup_class(cls):
        tf.keras.mixed_precision.set_global_policy('mixed_float16')

    @classmethod
    def teardown_class(cls):
        tf.keras.mixed_precision.set_global_policy('float32')


@pytest.mark.skipif(version(tf.version.VERSION) < version("2.4.0"),
                    reason="This test is enabled only when tensorflow version is 2.4.0+.")
class TestSaliencyWithMultipleOutputsModelOnMixedPrecision(TestSaliencyWithMultipleOutputsModel):
    @classmethod
    def setup_class(cls):
        tf.keras.mixed_precision.set_global_policy('mixed_float16')

    @classmethod
    def teardown_class(cls):
        tf.keras.mixed_precision.set_global_policy('float32')


@pytest.mark.skipif(version(tf.version.VERSION) < version("2.4.0"),
                    reason="This test is enabled only when tensorflow version is 2.4.0+.")
class TestSaliencyWithMultipleIOModelOnMixedPrecision(TestSaliencyWithMultipleIOModel):
    @classmethod
    def setup_class(cls):
        tf.keras.mixed_precision.set_global_policy('mixed_float16')

    @classmethod
    def teardown_class(cls):
        tf.keras.mixed_precision.set_global_policy('float32')


@pytest.mark.skipif(version(tf.version.VERSION) < version("2.4.0"),
                    reason="This test is enabled when tensorflow version is 2.4.0+.")
class TestMixedPrecision():
    def test__call__with_single_io(self, tmpdir):
        # Create and save lower precision model
        set_global_policy('mixed_float16')
        model = mock_conv_model()
        self._test_for_single_io(model)
        path = tmpdir.mkdir("tf-keras-vis").join("single_io.h5")
        model.save(path)
        # Load and test lower precision model on lower precision environment
        model = load_model(path)
        self._test_for_single_io(model)
        # Load and test lower precision model on full precision environment
        set_global_policy('float32')
        model = load_model(path)
        self._test_for_single_io(model)

    def test__call__with_float32_output_model(self, tmpdir):
        # Create and save lower precision model
        set_global_policy('mixed_float16')
        model = mock_conv_model_with_float32_output()
        self._test_for_single_io(model)
        path = tmpdir.mkdir("tf-keras-vis").join("float32_output.h5")
        model.save(path)
        # Load and test lower precision model on lower precision environment
        model = load_model(path)
        self._test_for_single_io(model)
        # Load and test lower precision model on full precision environment
        set_global_policy('float32')
        model = load_model(path)
        self._test_for_single_io(model)

    def _test_for_single_io(self, model):
        saliency = Saliency(model)
        result = saliency(CategoricalScore(0), dummy_sample((1, 8, 8, 3)))
        assert result.shape == (1, 8, 8)

    def test__call__with_multiple_io(self, tmpdir):
        # Create and save lower precision model
        set_global_policy('mixed_float16')
        model = mock_multiple_io_model()
        self._test_for_multiple_io(model)
        path = tmpdir.mkdir("tf-keras-vis").join("multiple_io.h5")
        model.save(path)
        # Load and test lower precision model on lower precision environment
        model = load_model(path)
        self._test_for_multiple_io(model)
        # Load and test lower precision model on full precision environment
        set_global_policy('float32')
        model = load_model(path)
        self._test_for_multiple_io(model)

    def _test_for_multiple_io(self, model):
        saliency = Saliency(model)
        result = saliency(
            [CategoricalScore(0), CategoricalScore(0)],
            [dummy_sample((1, 8, 8, 3)), dummy_sample((1, 10, 10, 3))])
        assert len(result) == 2
        assert result[0].shape == (1, 8, 8)
        assert result[1].shape == (1, 10, 10)
