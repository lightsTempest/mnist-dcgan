import os

# Linear algebra and plotting
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm

import seaborn as sns

# Deep Learning library
from keras.layers import Input, Dense, Lambda, Flatten, Reshape
from keras.layers import Conv2D, Conv2DTranspose
from keras.models import Model
from keras import backend as K
from keras import metrics
from keras.datasets import mnist

# Import DCGAN
from models.mnist_dcgan import DCGAN

# Parameters

img_rows, img_cols, img_chns = 28, 28, 1
filters = 64
n_conv = 3
batch_size = 100
latent_dim = 2
intermediate_dim = 128
epochs = 5
epsilon_std = 1.0

WEIGHTS_FILE = 'mnist_vae.h5'

original_img_size = (img_rows, img_cols, img_chns)


# Build the Network

x = Input(shape=original_img_size)
conv_1 = Conv2D(img_chns, 
                kernel_size=(2, 2),
                padding='same',
                activation='relu')(x)
conv_2 = Conv2D(filters, 
                kernel_size=(2, 2),
                padding='same', activation='relu',
                strides=(2, 2))(conv_1)
conv_3 = Conv2D(filters, 
                kernel_size=n_conv,
                padding='same', activation='relu',
                strides=1)(conv_2)
conv_4 = Conv2D(filters, 
                kernel_size=n_conv,
                padding='same', activation='relu',
                strides=1)(conv_3)
flat = Flatten()(conv_4)
hidden = Dense(intermediate_dim, activation='relu')(flat)

z_mean = Dense(latent_dim)(hidden)
z_log_var = Dense(latent_dim)(hidden)


def sampling(args):
    z_mean, z_log_var = args
    epsilon = K.random_normal(shape=(K.shape(z_mean)[0], latent_dim), mean=0., stddev=epsilon_std)
    
    return z_mean + K.exp(z_log_var / 2) * epsilon

z = Lambda(sampling)([z_mean, z_log_var])


decoder_hid = Dense(intermediate_dim, activation='relu')
decoder_upsample = Dense(filters * 14 * 14, activation='relu')

output_shape = (batch_size, 14, 14, filters)

decoder_reshape = Reshape(output_shape[1:])
decoder_deconv_1 = Conv2DTranspose(filters,
                                   kernel_size=n_conv,
                                   padding='same',
                                   strides=1,
                                   activation='relu')
decoder_deconv_2 = Conv2DTranspose(filters,
                                   kernel_size=n_conv,
                                   padding='same',
                                   strides=1,
                                   activation='relu')

output_shape = (batch_size, 29, 29, filters)
decoder_deconv_3 = Conv2DTranspose(filters,
                                   kernel_size=(3, 3),
                                   strides=(2, 2),
                                   padding='valid',
                                   activation='relu')
decoder_mean_squash = Conv2D(img_chns, kernel_size=2, padding='valid', activation='sigmoid')

hid_decoded = decoder_hid(z)
up_decoded = decoder_upsample(hid_decoded)
reshape_decoded = decoder_reshape(up_decoded)
deconv_1_decoded = decoder_deconv_1(reshape_decoded)
deconv_2_decoded = decoder_deconv_2(deconv_1_decoded)
x_decoded_relu = decoder_deconv_3(deconv_2_decoded)
x_decoded_mean_squash = decoder_mean_squash(x_decoded_relu)

vae = Model(x, x_decoded_mean_squash)

xent_loss = img_rows * img_cols * metrics.binary_crossentropy(K.flatten(x), K.flatten(x_decoded_mean_squash))
kl_loss = - 0.5 * K.sum(1 + z_log_var - K.square(z_mean) - K.exp(z_log_var), axis=-1)
vae_loss = K.mean(xent_loss + kl_loss)

vae.add_loss(vae_loss)
vae.compile(loss=[None], optimizer='rmsprop')
vae.summary()

# Load dataset
(X_train, y_train), (X_test, y_test) = mnist.load_data()

# Preprocess data
X_train = X_train.astype('float32') / 255
X_test  = X_test.astype('float32') / 255

X_train = X_train[:,:,:,None]
X_test  = X_test[:,:,:,None]


def classify_with_confidence(latent_vectors):
    def _get_gaussian(digit):
        idx = [i for i in range(y_test.shape[0]) if y_test[i] == digit]
        latent_vectors = x_test_encoded[idx]
        
        mu = np.mean(latent_vectors, axis=0)
        sigma = np.cov(latent_vectors.T)
        
        return lambda x : (1 / (2*np.pi) * np.sqrt(np.linalg.det(sigma))) * np.exp( -0.5 * (x - mu).dot(np.linalg.inv(sigma)).dot((x - mu).T))

    DIGITS = [i for i in range(10)]
    GAUSSIANS = dict([[i, _get_gaussian(i)] for i in DIGITS])

    classifications = []
    for x in latent_vectors:
        max_label = -1
        max_classif = -1
        for label, gaussian in GAUSSIANS.items():
            classif = gaussian(x)
            if classif > max_classif:
                max_label = label
                max_classif = classif
        classifications.append(max_label)
    return classifications

        


# Train the model

with tf.device('/gpu:0'):
    if os.path.exists(WEIGHTS_FILE):
        vae.load_weights(WEIGHTS_FILE)
    else:
        vae.fit(X_train,
                shuffle=True,
                epochs=epochs,
                batch_size=batch_size,
                validation_data=(X_test, None))
        vae.save(WEIGHTS_FILE)


    dcgan = DCGAN()
    dcgan.train(epochs=4000, batch_size=128, save_interval=50)

    encoder = Model(x, z_mean)

    x_gen_imgs = dcgan.generate_sample(10000)
    x_encoded_imgs = encoder.predict(x_gen_imgs, batch_size=10000)

    classified_imgs = classify_with_confidence(latent_vectors)

    plt.hist(classified_imgs)
    plt.show()