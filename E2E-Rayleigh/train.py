import os

os.environ['KERAS_BACKEND'] = 'tensorflow'
from keras.utils import to_categorical
from keras.layers import Dense, Dropout, Lambda, BatchNormalization, Input, Conv1D, TimeDistributed, Flatten, Activation,Conv2D
from keras.models import Model
from keras.callbacks import EarlyStopping, TensorBoard, History, ModelCheckpoint, ReduceLROnPlateau
from keras import backend as KR
import numpy as np
import copy
import time
import matplotlib.pyplot as plt
from keras.optimizers import Adam

'''
 --- COMMUNICATION PARAMETERS ---
'''

# Bits per Symbol
k = 4

# Number of symbols
L = 50

# Channel Use
n = 3

# Effective Throughput
#  (bits per symbol)*( number of symbols) / channel use
R = k / n

# Eb/N0 used for training
train_Eb_dB = 12

# Noise Standard Deviation
noise_sigma = np.sqrt(1 / (2 * R * 10 ** (train_Eb_dB / 10)))


# Number of messages used for training, each size = k*L
batch_size = 128

nb_train_word = batch_size*200

'''
 --- GENERATING INPUT DATA ---
'''

# Generate training binary Data
train_data = np.random.randint(low=0, high=2, size=(nb_train_word, k * L))
# Used as labeled data
label_data = copy.copy(train_data)
train_data = np.reshape(train_data, newshape=(nb_train_word, L, k))

# Convert Binary Data to integer
tmp_array = np.zeros(shape=k)
for i in range(k):
    tmp_array[i] = 2 ** i
int_data = tmp_array[::-1]

# Convert Integer Data to one-hot vector
int_data = np.reshape(int_data, newshape=(k, 1))
one_hot_data = np.dot(train_data, int_data)
vec_one_hot = to_categorical(y=one_hot_data, num_classes=2 ** k)

# used as Label data
label_one_hot = copy.copy(vec_one_hot)

'''
 --- NEURAL NETWORKS PARAMETERS ---
'''

early_stopping_patience = 100

epochs = 250

optimizer = Adam(lr=0.001)

early_stopping = EarlyStopping(monitor='val_loss',
                               patience=early_stopping_patience)


# Learning Rate Control
reduce_lr = ReduceLROnPlateau(monitor='loss', factor=0.1,
                              patience=5, min_lr=0.0001)

# Save the best results based on Training Set
modelcheckpoint = ModelCheckpoint(filepath='./' + 'model_LBC_' + str(k) + '_' + str(L) + '_' + str(n) + '_' + str(train_Eb_dB) + 'dB' + ' ' + 'Rayleigh ' + '.h5',
                                  monitor='loss',
                                  verbose=1,
                                  save_best_only=True,
                                  save_weights_only=True,
                                  mode='auto', period=1)



# Define Power Norm for Tx
def normalization(x):
    mean = KR.mean(x ** 2)
    return x / KR.sqrt(2 * mean)  # 2 = I and Q channels

def complex_multi(h,x):

    # ---- For Complex Number multiply of h*x
    # (a+bi)*(c+di) = (ac-bd)+(bc+ad)i
    # construct h1[c,-d]
    tmp_array = KR.ones(shape=(KR.shape(x)[0], L, 1))
    n_sign_array = KR.concatenate([tmp_array, -tmp_array], axis=2)
    h1 = h * n_sign_array

    # construct h2
    h2 = KR.reverse(h, axes=2)

    # ac - bd
    tmp = h1 * x
    h1x = KR.sum(tmp, axis=-1)

    # bc + ad
    tmp = h2 * x
    h2x = KR.sum(tmp, axis=-1)

    a_real = KR.expand_dims(h1x, axis=2)
    a_img = KR.expand_dims(h2x, axis=2)

    a_complex_array = KR.concatenate([a_real, a_img], axis=-1)

    return a_complex_array


# Define Channel Layers
#  x: input data
#  sigma: noise std
def channel_layer(x, sigma):
    # Init output tensor
    a_complex = []

    # AWGN noise
    w = KR.random_normal(KR.shape(x), mean=0.0, stddev=sigma)
    h = KR.random_normal(KR.shape(x), mean=0.0, stddev=np.sqrt(1 / 2))

    # support different channel use (n)
    for i in range(0,2*n,2):

        y_h = complex_multi(h[:,:,i:i+2],x[:,:,i:i+2])

        if i ==0:
            a_complex = y_h
        else:
            a_complex = KR.concatenate([a_complex,y_h],axis=-1)

    # Feed perfect CSI and HS+n to the receiver
    result = KR.concatenate([a_complex+w,h],axis=-1)

    return result



model_input = Input(batch_shape=(None, L, 2 ** k), name='input_bits')
e = Conv1D(filters=256, strides=1, kernel_size=5, padding = 'same', name='e_1')(model_input)
e = BatchNormalization(name='e_2')(e)
e = Activation('elu', name='e_3')(e)
e = Conv1D(filters=128, strides=1, kernel_size=3, padding = 'same', name='e_4')(e)
e = BatchNormalization(name='e_5')(e)
e = Activation('elu', name='e_6')(e)
e = Conv1D(filters=64, strides=1, kernel_size=3, padding = 'same', name='e_7')(e)  
e = BatchNormalization(name='e_8')(e)
e = Activation('elu', name='e_9')(e)
e = Conv1D(filters=2, strides=1, kernel_size=3, padding = 'same', name='e_10')(e)
e = BatchNormalization(name='e_11')(e)
e = Activation('linear', name='e_12')(e)
e = Lambda(normalization, name='power_norm')(e)


# Rayleigh + AWGN channel + h(CSI)
y_h = Lambda(channel_layer, arguments={'sigma': noise_sigma}, name='channel_layer')(e)

# Define Decoder Layers (Receiver)
d = Conv1D(filters=256, strides=1, kernel_size=5, padding = 'same', name='d_1')(y_h)
d = BatchNormalization(name='d_2')(d)
d = Activation('elu', name='d_3')(d)
d = Conv1D(filters=128, strides=1, kernel_size=3, padding = 'same', name='d_4')(d)
d = BatchNormalization(name='d_5')(d)
d = Activation('elu', name='d_6')(d)
d = Conv1D(filters=64, strides=1, kernel_size=3, padding = 'same', name='d_7')(d)
d = BatchNormalization(name='d_8')(d)
d = Activation('elu', name='d_9')(d)
d = Conv1D(filters=16, strides=1, kernel_size=3, padding = 'same', name='d_10')(d)
d = BatchNormalization(name='d_11')(d)
d = Activation('elu', name='d_12')(d)

# Output One hot vector and use Softmax to soft decoding
model_output = Conv1D(filters=2 ** k, strides=1, kernel_size=1, name='d_10', activation='softmax')(d)

# Build System Model
sys_model = Model(model_input, model_output)
encoder = Model(model_input, e)

# Print Model Architecture
sys_model.summary()


# Compile Model
sys_model.compile(optimizer=optimizer, loss='binary_crossentropy', metrics=['accuracy'])
# print('encoder output:', '\n', encoder.predict(vec_one_hot, batch_size=batch_size))

print('starting train the NN...')
start = time.clock()

# TRAINING
mod_history = sys_model.fit(vec_one_hot, label_one_hot,
                            batch_size=batch_size,
                            epochs=epochs,
                            verbose=1,
                            validation_split=None, callbacks=[modelcheckpoint,reduce_lr])

end = time.clock()

print('The NN has trained ' + str(end - start) + ' s')


# Plot the Training Loss and Validation Loss
hist_dict = mod_history.history

# val_loss = hist_dict['val_loss']
loss = hist_dict['loss']
acc = hist_dict['acc']
# val_acc = hist_dict['val_acc']
print(loss)
epoch = np.arange(1, epochs + 1)

# plt.semilogy(epoch,val_loss,label='val_loss')
plt.semilogy(epoch, loss, label='loss')

plt.legend(loc=0)
plt.grid('true')
plt.xlabel('epochs')
plt.ylabel('Binary cross-entropy loss')
plt.savefig('Training and Validation loss(No channel model)')
plt.show()
