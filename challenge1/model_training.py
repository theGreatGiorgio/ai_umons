"""Train a deep neural network for genre classification, based on Xception

Usage:
    model_training.py [--mode=<mode_name>] [--weights <path_to_weights>] [--wiki_shift=<i>]
    model_training.py [--mode=<mode_name>] [--weights <path_to_weights>] [--memmaps_directory <path>]
    model_training.py (--export_model) (--weights <path_to_weights>) (--out <output_name>)
    model_training.py (-h | --help)

Options:
-h --help                                    Display help.
--load_model <model_name>                    Train a model already saved.
--mode=<mode_name>                           Choose the training mode (init, main-training, fine-tuning ) [default : init].
--weights <path_to_weights>                  Load pre-trained weights (from a checkpoint, for example).
--wiki_shift=<i>                             Data set shift [default: 0]
--memmaps_directory <path>                   Path to mmemaps directory. If this option is specified, the only dataset loaded is from the memmaps. [default: Dataset]
--export_model                               Export a model from weights. The options weights and output must be specified.
-o --out <output_name>                    Name of the saved model if the option export_model is specified.

Note : The memmaps have to be named (training|testing)_(images|genders|ages)
"""
import os
import sys
#from keras.applications.inception_resnet_v2 import InceptionResNetV2
from time import time
from keras.applications.xception import Xception
from keras.models import Model
from keras.layers import Dense, GlobalAveragePooling2D
from keras.preprocessing.image import ImageDataGenerator, array_to_img, img_to_array, load_img
import numpy as np
from keras.utils.np_utils import to_categorical
from keras.callbacks import TensorBoard
from keras.models import model_from_json
from keras.callbacks import ModelCheckpoint
from scipy.io import loadmat
from PIL import Image
import cv2
from docopt import docopt

DATABASE_SIZE = 43390
EPOCHS = 0
BATCH_SIZE = 20
STEPS_PER_EPOCH = DATABASE_SIZE // (10 * BATCH_SIZE)
VALIDATION_STEPS = STEPS_PER_EPOCH // 10
gender_dict = {'m': 0, 'f' : 1}
CUSTOM_SAVE_PATH = '.'
MAT_PATH = 'wiki'

def load_data(mat_path):
    d = loadmat(mat_path)

    return d["image"], d["gender"][0], d["age"][0], d["db"][0], d["img_size"][0, 0], d["min_score"][0, 0]

def save(model, path='.', model_name='xception_gender'):
    # serialize model to JSON
    model_json = model.to_json()
    with open("{}/models/{}.json".format(path, model_name), "w") as json_file:
        json_file.write(model_json)
    # serialize weights to HDF5
    model.save_weights("{}/models/{}.h5".format(path, model_name))
    print("Saved model to disk : {}".format(path))
    if path != '.':
        save(model, path='.', model_name=model_name)

def preprocess_input(x):
    x = np.array(x, dtype=float)
    x /= 255.
    x -= 0.5
    x *= 2.
    return x

def load_openu_batch(info, path, datagen=None):
    # OpenU Dataset
    #with open('{}/{}_info.txt'.format(path, mode), 'r') as info:
    X = np.empty([BATCH_SIZE, 299, 299, 3])
    Y = np.empty([BATCH_SIZE], dtype='uint8')
    for batch_step in range(BATCH_SIZE):
        line = info.readline().strip()
        if not line:
            return None, None
        img_name, gender, age = line.split(' ; ')
        img = load_img('{}/all/{}'.format(path, img_name), target_size=(299, 299))
        x = img_to_array(img)
        X[batch_step] = x
        Y[batch_step] = gender_dict[gender]

        if batch_step == BATCH_SIZE - 1:
            if datagen:
                X, Y = datagen.flow(x=X, y=Y, batch_size=BATCH_SIZE,
                        #save_to_dir='sorted_faces/gen'
                        ).next()
            return preprocess_input(X), Y

def generate_dataset_from_files(path='sorted_faces/train', mode='train', rotations=False):
    args = docopt(__doc__)
    shift = int(args['--wiki_shift'])
    datagen = ImageDataGenerator(
            width_shift_range=0.1,
            height_shift_range=0.1,
            #rotation_range=30,
            zoom_range=0.3,
            horizontal_flip=True,
            ) if rotations else None
    try:
        while 1:
            info = open('{}/{}_info.txt'.format(path, mode), 'r')
            assert os.path.exists(MAT_PATH)
            if mode == 'train':
                for i in range(9):
                    i = (i + shift) % 9
                    print("\nTraining on Wiki data base : part. {}".format(i))
                    image, gender, _, _, _, _ = load_data('{}/wiki-part{}.mat'.format(MAT_PATH, i))
                    part = len(image) // BATCH_SIZE
                    for j in range(part):
                        X, Y = load_openu_batch(info, path, datagen)
                        if X is not None and Y is not None:
                            yield(X, Y)
                        else:
                            info.close()
                            info = open('{}/{}_info.txt'.format(path, mode), 'r')
                        X, Y = None, None # free memory
                        X = np.array([cv2.cvtColor(x, cv2.COLOR_BGR2RGB) for x in image[j * BATCH_SIZE : (j + 1) * BATCH_SIZE]])
                        #in the databse : 0 for female, 1 for male
                        Y = np.array([(y + 1) % 2 for y in gender[j * BATCH_SIZE : (j + 1) * BATCH_SIZE]], dtype='uint8')
                        if rotations:
                            X, Y = datagen.flow(x=X, y=Y, batch_size=BATCH_SIZE,
                                    #save_to_dir='sorted_faces/gen'
                                    ).next()
                        #Image.fromarray(np.array(X[0], dtype='uint8')).show()
                        yield (preprocess_input(X), Y)
                        X, Y = None, None

                    image, gender = None, None

            elif mode == 'valid':
                image, gender, _, _, _, _ = load_data('{}/wiki-part{}.mat'.format(MAT_PATH, 9))
                part = int(len(image)/BATCH_SIZE)
                for j in range(part):
                    X, Y = load_openu_batch(info, path, datagen)
                    if X is not None and Y is not None:
                        yield(X, Y)
                    else:
                        info.close()
                        info = open('{}/{}_info.txt'.format(path, mode), 'r')
                    X, Y = None, None # free memory
                    X = np.array([cv2.cvtColor(x, cv2.COLOR_BGR2RGB) for x in image[j * BATCH_SIZE : (j + 1) * BATCH_SIZE]])
                    #in the databse : 0 for female, 1 for male
                    Y = np.array([(y + 1) % 2 for y in gender[j * BATCH_SIZE : (j + 1) * BATCH_SIZE]], dtype='uint8')
                    if rotations:
                        X, Y = datagen.flow(x=X, y=Y, batch_size=BATCH_SIZE,
                                #save_to_dir='sorted_faces/gen'
                                ).next()
                    yield (preprocess_input(X), Y)
                    X, Y = None, None

                image, gender = None, None
    finally:
        print("\nCancelled.\nOpenU dataset training file closed.\n")
        info.close()

def generate_dataset(path='sorted_faces/train', mode='train', rotations=False):
    datagen = ImageDataGenerator(
            width_shift_range=0.1,
            height_shift_range=0.1,
            #rotation_range=30,
            zoom_range=0.3,
            horizontal_flip=True,
            ) if rotations else None
    args = docopt(__doc__)
    if args['--memmaps_directory']:
        print("Found memmaps in : {}".format(args[('--memmaps_directory')]))
        while(1):
            if mode == 'train':
                length = 43390
                X_train = np.memmap('{}/training_images'.format(args['--memmaps_directory']), dtype='uint8', mode='r', shape=(length, 299, 299, 3))
                Y_train = np.memmap('{}/training_genders'.format(args['--memmaps_directory']), dtype='uint8', mode='r', shape=(length))
                for i in range(length // BATCH_SIZE):
                    X = np.array(X_train[i * BATCH_SIZE : (i + 1) * BATCH_SIZE], dtype='uint8')
                    Y = np.array(Y_train[i * BATCH_SIZE : (i + 1) * BATCH_SIZE], dtype='uint8')
                    if rotations:
                        X, Y = datagen.flow(x=X, y=Y, batch_size=BATCH_SIZE,
                                ).next()
                    yield preprocess_input(X), Y
            elif mode == 'valid':
                #length = 6943
                length = VALIDATION_STEPS * BATCH_SIZE
                X_test = np.memmap('{}/testing_images'.format(args['--memmaps_directory']), dtype='uint8', mode='r', shape=(length, 299, 299, 3))
                Y_test = np.memmap('{}/testing_genders'.format(args['--memmaps_directory']), dtype='uint8', mode='r', shape=(length))
                for i in range(length // BATCH_SIZE):
                    X = np.array(X_test[i * BATCH_SIZE : (i + 1) * BATCH_SIZE], dtype='uint8')
                    Y = np.array(Y_test[i * BATCH_SIZE : (i + 1) * BATCH_SIZE], dtype='uint8')
                    #   if rotations:
                    #       X, Y = datagen.flow(x=X, y=Y, batch_size=BATCH_SIZE,
                    #               ).next()
                    yield preprocess_input(X), Y
    else :
        generate_dataset_from_files(path, mode, rotations)


def fine_tuning(weights=''):
    print("model initialisation (Xception based) for fine tuning...")
    base_model = Xception(include_top=False, input_shape=(299, 299, 3))

    # let's visualize layer names and layer indices
    for i, layer in enumerate(base_model.layers):
       print(i, layer.name)

    # add a global spatial average pooling layer
    x = base_model.output
    x = GlobalAveragePooling2D()(x)
    # let's add two fully-connected layer
    x = Dense(299, activation='relu')(x)
    # and a logistic layer ; we have 2 classes
    predictions = Dense(1, activation='sigmoid')(x)

    # this is the model we will train
    model = Model(inputs=base_model.input, outputs=predictions)

    if weights:
        model.load_weights(weights)
        print('weights ({}) loaded !'.format(weights))

    # We will freeze the bottom N layers
    # and train the remaining top layers.

    # let's visualize layer names and layer indices
    for i, layer in enumerate(model.layers):
       print(i, layer.name)

    # we chose to train the top 2 inception blocks, i.e. we will freeze
    # the first 249 layers and unfreeze the rest:
    for layer in model.layers[:55]:
       layer.trainable = False
    for layer in model.layers[55:]:
       layer.trainable = True

    # we need to recompile the model for these modifications to take effect
    # we use SGD with a low learning rate
    from keras.optimizers import SGD
    model.compile(optimizer=SGD(lr=0.0001, momentum=0.9), loss='binary_crossentropy', metrics=['accuracy'])

    # we train our model again (this time fine-tuning the top 2 inception blocks
    # alongside the top Dense layers
    print("\n")
    print("Fine tuning phase")

    # Callbacks
    if not os.path.exists('{}/weights'.format(CUSTOM_SAVE_PATH)):
        os.makedirs("{}/weights".format(CUSTOM_SAVE_PATH))

    filepath= CUSTOM_SAVE_PATH + "/weights/fine_tuning_weights-{epoch:02d}-{val_acc:.2f}.hdf5"
    checkpoint = ModelCheckpoint(filepath, monitor='val_acc', verbose=1, save_best_only=True, mode='max')
    tensorboard = TensorBoard(log_dir='{}/logs/fine_tuning_gender{}'.format(CUSTOM_SAVE_PATH, time()))#, histogram_freq=1, write_grads=True, batch_size=BATCH_SIZE)

    # Fit
    model.fit_generator(generate_dataset(rotations=True), steps_per_epoch=STEPS_PER_EPOCH,
                        validation_data=generate_dataset(path='sorted_faces/valid', rotations=True),
                        validation_steps=VALIDATION_STEPS,
                        epochs=EPOCHS, callbacks=[tensorboard, checkpoint])
    save(model, path=CUSTOM_SAVE_PATH, model_name='xception_gender')

def main_training(weights=''):
    print("model initialisation (Xception based) ...")
    base_model = Xception(include_top=False, input_shape=(299, 299, 3))

    # let's visualize layer names and layer indices
    for i, layer in enumerate(base_model.layers):
       print(i, layer.name)

    # add a global spatial average pooling layer
    x = base_model.output
    x = GlobalAveragePooling2D()(x)
    # let's add two fully-connected layer
    x = Dense(299, activation='relu')(x)
    # and a logistic layer ; we have 2 classes
    predictions = Dense(1, activation='sigmoid')(x)

    # this is the model we will train
    model = Model(inputs=base_model.input, outputs=predictions)

    if weights:
        model.load_weights(weights)
        print('weights ({}) loaded !'.format(weights))

    for layer in model.layers[:115]:
       layer.trainable = False
    for layer in model.layers[115:]:
       layer.trainable = True

    # compile the model (should be done *after* setting layers to non-trainable)
    model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

    print("\nTop layers fitting phase (with datagenerator)")

    # Callbacks
    if not os.path.exists('{}/weights'.format(CUSTOM_SAVE_PATH)):
        os.makedirs("{}/weights".format(CUSTOM_SAVE_PATH))

    filepath= CUSTOM_SAVE_PATH + "/weights/main_training_weights-improvement-{epoch:02d}-{val_acc:.2f}.hdf5"
    checkpoint = ModelCheckpoint(filepath, monitor='val_acc', verbose=1, save_best_only=True, mode='max')
    tensorboard = TensorBoard(log_dir='{}/logs/gender{}'.format(CUSTOM_SAVE_PATH, time()))#, histogram_freq=1, write_grads=True, batch_size=BATCH_SIZE)

    # Fit
    model.fit_generator(generate_dataset(rotations=True), steps_per_epoch=STEPS_PER_EPOCH,
                        validation_data=generate_dataset(path='sorted_faces/valid',
                                                         mode='valid', rotations=True),
                        validation_steps=VALIDATION_STEPS,
                        epochs=EPOCHS, callbacks=[tensorboard, checkpoint])

    # at this point, the top layers are well trained and we can start fine-tuning
    save(model, path=CUSTOM_SAVE_PATH, model_name='xception_gender_main')

def model_initialisation_phase():
    print("model initialisation (Xception based) ...")
    base_model = Xception(include_top=False)

    # let's visualize layer names and layer indices
    for i, layer in enumerate(base_model.layers):
       print(i, layer.name)

    # add a global spatial average pooling layer
    x = base_model.output
    x = GlobalAveragePooling2D()(x)
    # let's add a fully-connected layer
    x = Dense(100, activation='relu')(x)
    # and a logistic layer ; we have 2 classes
    predictions = Dense(1, activation='sigmoid')(x)

    # this is the model we will train
    model = Model(inputs=base_model.input, outputs=predictions)

    # first: train only the top layers (which were randomly initialized)
    # i.e. freeze all convolutional InceptionV3 layers
    for layer in base_model.layers:
        layer.trainable = False

    # compile the model (should be done *after* setting layers to non-trainable)
    model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

    # train the model on the new data for a few epochs
    # Example : model.fit_generator(generate_arrays_from_file('/my_file.txt'),
    #                    steps_per_epoch=1000, epochs=10)
    print("\nTop layers fitting phase")

    tensorboard = TensorBoard(log_dir='{}/logs/{}'.format(CUSTOM_SAVE_PATH, time()))#, histogram_freq=1, write_grads=True, batch_size=BATCH_SIZE)

    model.fit_generator(generate_dataset(), steps_per_epoch=STEPS_PER_EPOCH, epochs=10, callbacks=[tensorboard])
    #validation_data=generate_dataset('sorted_faces/valid', 'valid'), validation_steps=200)

    # at this point, the top layers are well trained and we can start fine-tuning
    save(model, path=CUSTOM_SAVE_PATH, model_name='xception_gender_init')

def export_from_weights(weights_path, name):
    print("Export model from weights (Xception based) ...")
    base_model = Xception(include_top=False, input_shape=(299, 299, 3))

    # add a global spatial average pooling layer
    x = base_model.output
    x = GlobalAveragePooling2D()(x)
    # let's add two fully-connected layer
    x = Dense(299, activation='relu')(x)
    # and a logistic layer ; we have 2 classes
    predictions = Dense(1, activation='sigmoid')(x)

    # this is the model we will train
    model = Model(inputs=base_model.input, outputs=predictions)

    model.load_weights(weights_path)
    print('weights ({}) loaded !'.format(weights_path))
    save(model, path=CUSTOM_SAVE_PATH, model_name=name)


if __name__ == '__main__':
    if not os.path.exists('{}/logs'.format(CUSTOM_SAVE_PATH)):
        os.makedirs("{}/logs".format(CUSTOM_SAVE_PATH))
    if not os.path.exists('{}/models'.format(CUSTOM_SAVE_PATH)):
        os.makedirs("{}/models".format(CUSTOM_SAVE_PATH))

    args = docopt(__doc__)
    mode = args['--mode']
    weights = args['--weights']

    if args['--export_model']:
        export_from_weights(weights, args['--out'])
    elif mode == 'fine-tuning':
        fine_tuning(weights)
    elif mode == 'main-training':
        main_training(weights)
        fine_tuning('{}/models/xception_gender_main.h5'.format(CUSTOM_SAVE_PATH))
    else:
        # model_initialisation_phase() # deprecated
        main_training()
        fine_tuning('{}/models/xception_gender_main.h5'.format(CUSTOM_SAVE_PATH))
