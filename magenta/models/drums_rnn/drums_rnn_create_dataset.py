# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Create a dataset of SequenceExamples from NoteSequence protos.

This script will extract drum tracks from NoteSequence protos and save them to
TensorFlow's SequenceExample protos for input to the drums RNN models.
"""

import os

# internal imports
import tensorflow as tf
import magenta

from magenta.models.drums_rnn import drums_rnn_config_flags

from magenta.pipelines import dag_pipeline
from magenta.pipelines import drum_pipelines
from magenta.pipelines import pipeline
from magenta.pipelines import pipelines_common
from magenta.protobuf import music_pb2

FLAGS = tf.app.flags.FLAGS
tf.app.flags.DEFINE_string('input', None,
                           'TFRecord to read NoteSequence protos from.')
tf.app.flags.DEFINE_string('output_dir', None,
                           'Directory to write training and eval TFRecord '
                           'files. The TFRecord files are populated with '
                           'SequenceExample protos.')
tf.app.flags.DEFINE_float('eval_ratio', 0.1,
                          'Fraction of input to set aside for eval set. '
                          'Partition is randomly selected.')
tf.app.flags.DEFINE_string('log', 'INFO',
                           'The threshold for what messages will be logged '
                           'DEBUG, INFO, WARN, ERROR, or FATAL.')


class EncoderPipeline(pipeline.Pipeline):
  """A Module that converts drum tracks to a model specific encoding."""

  def __init__(self, config, name):
    """Constructs an EncoderPipeline.

    Args:
      config: A DrumsRnnConfig that specifies the encoder/decoder.
      name: A unique pipeline name.
    """
    super(EncoderPipeline, self).__init__(
        input_type=magenta.music.DrumTrack,
        output_type=tf.train.SequenceExample,
        name=name)
    self._drums_encoder_decoder = config.encoder_decoder

  def transform(self, drums):
    encoded = self._drums_encoder_decoder.encode(drums)
    return [encoded]

  def get_stats(self):
    return {}


def get_pipeline(config, eval_ratio):
  """Returns the Pipeline instance which creates the RNN dataset.

  Args:
    config: A DrumsRnnConfig object.
    eval_ratio: Fraction of input to set aside for evaluation set.

  Returns:
    A pipeline.Pipeline instance.
  """
  quantizer = pipelines_common.Quantizer(steps_per_quarter=4)
  drums_extractor_train = drum_pipelines.DrumsExtractor(
      min_bars=7, max_steps=512, gap_bars=1.0, name='DrumsExtractorTrain')
  drums_extractor_eval = drum_pipelines.DrumsExtractor(
      min_bars=7, max_steps=512, gap_bars=1.0, name='DrumsExtractorEval')
  encoder_pipeline_train = EncoderPipeline(config, name='EncoderPipelineTrain')
  encoder_pipeline_eval = EncoderPipeline(config, name='EncoderPipelineEval')
  partitioner = pipelines_common.RandomPartition(
      music_pb2.NoteSequence,
      ['eval_drum_tracks', 'training_drum_tracks'],
      [eval_ratio])

  dag = {quantizer: dag_pipeline.Input(music_pb2.NoteSequence),
         partitioner: quantizer,
         drums_extractor_train: partitioner['training_drum_tracks'],
         drums_extractor_eval: partitioner['eval_drum_tracks'],
         encoder_pipeline_train: drums_extractor_train,
         encoder_pipeline_eval: drums_extractor_eval,
         dag_pipeline.Output('training_drum_tracks'): encoder_pipeline_train,
         dag_pipeline.Output('eval_drum_tracks'): encoder_pipeline_eval}
  return dag_pipeline.DAGPipeline(dag)


def main(unused_argv):
  tf.logging.set_verbosity(FLAGS.log)

  config = drums_rnn_config_flags.config_from_flags()
  pipeline_instance = get_pipeline(
      config, FLAGS.eval_ratio)

  FLAGS.input = os.path.expanduser(FLAGS.input)
  FLAGS.output_dir = os.path.expanduser(FLAGS.output_dir)
  pipeline.run_pipeline_serial(
      pipeline_instance,
      pipeline.tf_record_iterator(FLAGS.input, pipeline_instance.input_type),
      FLAGS.output_dir)


def console_entry_point():
  tf.app.run(main)


if __name__ == '__main__':
  console_entry_point()
