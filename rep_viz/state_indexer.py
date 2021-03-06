import tensorflow as tf
import numpy as np
from image_loader import ImageLoader
from harpreif.image_utils import sliding_window, gradient_discretizer
from skimage.feature import hog
import cPickle as Pickle
from harpreif.myconstants import *
from model.creator import Creator
from scipy.misc import imresize


class Image2Feature(Creator):
    def __init__(self, image_dir, checkpoint_dir, checkpoint_iter, num_actions, num_gradients, state_type):
        """

        :param image_dir: The test directory for images
        :param checkpoint_dir: The checkpoint containing the best learnt model weights and biases
        :param num_actions: Number of actions that the agent can take
        :param num_gradients: Number of gradients to be used for each window
        :param state_type: 'hog' for using windowed HOG gradient as state, 'image' for using raw images itself
        """
        self.state_type = state_type
        self.image_dir = image_dir
        self.bins = np.array([x / float(NUM_BINS) for x in range(0, NUM_BINS, 1)])
        self.sess = None
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_iter = checkpoint_iter
        self.num_actions = num_actions
        self.num_gradients = num_gradients
        if self.state_type == 'hog':
            self.input_channels = self.num_gradients
        elif self.state_type == 'image':
            self.input_channels = 1
        else:
            raise ValueError('State type not recognized, enter hog or image')

        self.input_height = len(range(0, IMAGE_HEIGHT - SLIDING_STRIDE, SLIDING_STRIDE))
        self.input_width = self.input_height
        self.imagenet = None
        # self.feature_dict = dict()
        self.state_height = self.input_height
        self.state_width = self.state_height
        self.save_transform = True
        self.im2f_loc = None
        self.feature_size = None
        Creator.__init__(self, self.input_channels, self.num_actions, self.input_height, self.input_width)

    def __load_model(self):
        """
        Loads the model and populates it with checkpoint weights
        :return: None
        """
        print 'Initializing Session...'
        self.sess = tf.InteractiveSession()
        print 'Creating Network...'
        self.__create_network()
        print 'Populating Network with learned weights and biases...'
        self.__populate_network()

    def __load_images(self):
        """
        Loads the images into imagenet from which it can be queried
        :return: None
        """
        self.imagenet = ImageLoader(self.image_dir)

    def image2feature(self, save_transform=False, im2f_loc=None):
        """
        Transforms image to feature vector obtained from penultimate layer of dqn
        :param save_transform: True, if we wish to save the image 2 feature transform map
        :param im2f_loc: If save_transform == True, then this contains the location where to save the map
        :return: The image 2 feature map
        """
        print 'Loading The images...'
        self.__load_images()

        print 'Loading the model...'
        self.__load_model()

        print 'Obtaining and Returning the map for image to features...'
        self.save_transform = save_transform
        self.im2f_loc = im2f_loc
        return self.__save_and_get_features()

    def __create_network(self):
        """
        Creates the entire DQN network
        :return: None
        """
        self._initialize_weights_and_biases()
        self._form_input_layer()
        self._form_hidden_layers()
        self._form_output_layer()

    def __populate_network(self):
        """
        Popilates the network with checkpoint weights and biases
        :return: None
        """
        saver = tf.train.Saver()
        self.sess.run(tf.initialize_all_variables())
        checkpoint_name = self.checkpoint_dir + "saved_networks/" + "jigsaw-dqn-" + str(self.checkpoint_iter)
        checkpoint = tf.train.get_checkpoint_state(self.checkpoint_dir + "saved_networks")
        if checkpoint and (checkpoint_name in checkpoint.all_model_checkpoint_paths):
            saver.restore(self.sess, checkpoint_name)
            print("Successfully loaded:", checkpoint_name)
        else:
            raise ValueError("No checkpoint found. You must have saved weights")

    def __get_input_for_model(self, image):
        """
        Renders the new gamestate based on the changed board condition using HOG gradients over sliding window
        :return: None
        """
        state = None
        if self.state_type == 'hog':
            slides = sliding_window(image, SLIDING_STRIDE, WINDOW_SIZE)

            hog_gradients = []
            for slide in slides:
                window_image = slide[2]

                gradient = np.array(hog(window_image,
                                        orientations=self.num_gradients,
                                        pixels_per_cell=WINDOW_SIZE,
                                        cells_per_block=(1, 1), visualise=False))

                assert gradient.size == self.num_gradients, "Gradient size not equal to desired size"
                gradient = gradient_discretizer(gradient, self.bins)
                hog_gradients.extend(gradient)

            hog_gradients = np.array(hog_gradients)

            hog_gradients = hog_gradients.reshape((self.state_height, self.state_width, self.num_gradients))

            assert hog_gradients.shape == (self.input_height, self.input_width, self.input_channels), \
                "The state dimension is trying to be altered"
            state = hog_gradients

        elif self.state_type == 'image':
            resized_discrete_im = np.digitize(
                imresize(image, (self.state_height, self.state_width)),
                self.bins)
            state = np.array([resized_discrete_im]).transpose().swapaxes(0, 1)

        else:
            ValueError('The state type is not valid, enter "hog" or "image"')

        return state

    def __get_image_features(self):
        """
        Get the feature vector for all the images
        :return: None
        """
        feature_dict = dict()
        feature_size = 0

        while True:
            is_present = self.imagenet.load_next_image()

            if is_present:
                image_nm, image = self.imagenet.get_image()
                image_state = self.__get_input_for_model(image)
                im_feat = self.sess.run(self.h_fc2, feed_dict={self.s: [image_state]})
                feature_dict[image_nm] = im_feat
                if feature_size == 0:
                    feature_size = im_feat.size
            else:
                return feature_dict, feature_size

    def __save_and_get_features(self):
        """
        Saves and returns the feature map and feature size
        :return: (feature_map, feature_dimension)
        """
        feature_dict, feature_size = self.__get_image_features()
        if self.save_transform:
            Pickle.dump(feature_dict, open(self.im2f_loc + "image2feature.p", "wb"))
        return feature_dict, feature_size
