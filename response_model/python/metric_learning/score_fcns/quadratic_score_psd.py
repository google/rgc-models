# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
r"""Learn a score function of form s(x,y) = (x-y)'A(x-y) with A P.S.D.

Example of how to run :
metric_eval\
--model='quadratic_psd' --logtostderr --lam_l1=0 \
--data_path='/cns/oi-d/home/bhaishahster/metric_learning/'
'examples_pc2017_04_25_1/' --data_train='data012_lr_15_cells_groupb.mat' \
--data_test='data012_lr_15_cells_groupb_with_stimulus.mat' \
--save_suffix='_2017_04_25_1_cells_15_groupb' \
--gfs_user='foam-brain-gpu' --triplet_type='a'
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import numpy as np
import tensorflow as tf
import retina.response_model.python.metric_learning.score_fcns.quadratic_score as quad


class QuadraticScorePSD(quad.QuadraticScore):
  """Score of form x'Ax, with A P.S.D."""

  def _build_graph(self, n_cells, time_window, lr, lam_l1):
    """Build tensorflow graph.

    Args :
      n_cells : number of cells (int)
      time_window : number of time bins in each response vector (int)
      lr : learning rate (float)
      lam_l1 : regularization on entires of A (float)
    """

    # declare variables
    self.dim = n_cells*time_window
    self.lam_l1 = lam_l1
    self.A_symm = tf.Variable(0.001 * np.eye(self.dim).astype(np.float32),
                    name='A_symm') # initialize Aij to be zero

    # placeholders for anchor, pos and neg
    self.anchor = tf.placeholder(dtype=tf.float32,
                                 shape=[None, n_cells, time_window],
                                 name='anchor')
    self.pos = tf.placeholder(dtype=tf.float32,
                              shape=[None, n_cells, time_window], name='pos')
    self.neg = tf.placeholder(dtype=tf.float32,
                              shape=[None, n_cells, time_window], name='neg')

    self.score_anchor_pos = self.get_score(self.anchor, self.pos)
    self.score_anchor_neg = self.get_score(self.anchor, self.neg)

    self.get_loss()
    self.train_step = tf.train.AdagradOptimizer(lr).minimize(self.loss)

    # do projection to A_symm symmetric
    project_A_symm = tf.assign(self.A_symm,
                               (self.A_symm + tf.transpose(self.A_symm))/2)

    # remove negative eigen vectors.
    with tf.control_dependencies([project_A_symm]):
      e, v = tf.self_adjoint_eig(self.A_symm)
      e_pos = tf.nn.relu(e)
      A_symm_new = tf.matmul(tf.matmul(v, tf.diag(e_pos)), tf.transpose(v))
      project_A_PSD = tf.assign(self.A_symm, A_symm_new)

    # combine all projection operators into one.
    self.project_A = tf.group(project_A_symm, project_A_PSD)

  def get_loss(self):
    self.loss = (tf.reduce_sum(tf.nn.relu(self.score_anchor_pos -
                                          self.score_anchor_neg + 1)) +
                 self.lam_l1*tf.reduce_sum(tf.abs(self.A_symm)))

  def update(self, triplet_batch):
    """Given a batch of training data, update metric parameters.

    Args :
        triplet_batch : List [anchor, positive, negative], each with shape:
                        (batch x cells x time_window)
    Returns :
        loss : Training loss for the batch of data.
    """

    # make gradient step.
    feed_dict = {self.anchor: triplet_batch[0],
                 self.pos: triplet_batch[1],
                 self.neg: triplet_batch[2]}
    _, loss = self.sess.run([self.train_step, self.loss], feed_dict=feed_dict)

    # project into constraint set.
    self.sess.run(self.project_A)
    return loss



