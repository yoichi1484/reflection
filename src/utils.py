import gensim
import random
import json
import torch

path_dataset = '../data' 
path_w2v = '../data/GoogleNews-vectors-negative300.bin' 
path_glv = '../data/glove.42B.300d_gensim.txt' 


def load_word_embeddings(embedding):
    if embedding == 'word2vec':
        return gensim.models.KeyedVectors.load_word2vec_format(path_w2v, binary=True)
    elif embedding == 'glove':
        return gensim.models.KeyedVectors.load_word2vec_format(path_glv)
    

def reflection_numpy(x, a, c):
    '''
        Examples:
        >>> x = np.array([1,1])
        >>> a = np.array([1,1])
        >>> c = np.array([0,0])
        >>> reflection_numpy(x, a, c) 
            array([-1, -1])
    '''
    return x - 2 * (np.dot(x-c, a)/np.dot(a, a)) * a


def load_dataset(rate_invariant_words, attributes, seed, embedding):
    # Load A nad N dataset
    with open(path_dataset + '/datasets_' + embedding + '.json') as f:
        dataset = json.load(f)
    attribute_words = [d for d in dataset['A'] if d[1] in attributes]
    #invariant_words = [d for d in dataset['N'] if d[1] in attributes]
    invariant_words = [d for d in dataset['N_frequent_words'] if d[1] in attributes]
    invariant_words_train = [d for d in invariant_words if d[0] == 'train']
    invariant_words_test = [d for d in invariant_words if d[0] == 'test']
    
    # Sampling invariant words for training
    assert 0 <= rate_invariant_words <= 1
    num_invariant_words = int(rate_invariant_words * len(attribute_words))
    if num_invariant_words > len(invariant_words_train):
        num_invariant_words = len(invariant_words_train)
    random.seed(seed)
    invariant_words_train = random.sample(invariant_words_train, num_invariant_words)
    #print(len(attribute_words), len(invariant_words_train), len(invariant_words_test))
    return attribute_words + invariant_words_train + invariant_words_test
    
    
def get_device(gpu_id=-1):
    if gpu_id >= 0 and torch.cuda.is_available():
        print('device: gpu')
        return torch.device("cuda", gpu_id), True
    else:
        print('device: cpu')
        return torch.device("cpu"), False