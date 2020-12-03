import numpy as np
import argparse
import json
import os
import datetime
from tqdm import tqdm
import torch
#from torch.optim.lr_scheduler import StepLR
import utils
from nets import Ref_PM, Ref_PM_Share

ATTR2ID = {'MF':0, 'SP':1, 'CC':2, 'AN':3}


def add_noise_to_word_vec(wv, sigma):
    return wv + torch.from_numpy(sigma * np.random.randn(*wv.shape)).float()


def train(args, model, device, train_loader, optimizer, epoch):
    model.train()
    mse = torch.nn.MSELoss()
    train_loss = 0
    for batch_idx, (x, target, z) in enumerate(train_loader):
        x = add_noise_to_word_vec(x, args.sigma) # add noise
        x, z, target =  x.to(device), z.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(x, z)
        loss = mse(output, target)
        train_loss += loss
        loss.backward()
        optimizer.step()
        if args.dry_run:
            break
    return train_loss / len(train_loader.dataset)


def test(model, device, valid_loader, dtype):
    model.eval()
    mse = torch.nn.MSELoss() #reduction='sum')
    test_loss = 0
    with torch.no_grad():
        for x, target, z in valid_loader:
            x, z, target =  x.to(device), z.to(device), target.to(device)
            output = model(x, z)
            test_loss += mse(output, target) # sum up batch loss
    return test_loss / len(valid_loader.dataset)
    

def main():
    # Training settings
    parser = argparse.ArgumentParser(description='PyTorch Reflection-based Word Attribute Transfer Example')
    parser.add_argument('--emb', type=str, default='word2vec', 
                        help='word embeddings: word2vec or glove (default: word2vec)')
    parser.add_argument('--attr', type=str, default='MF', 
                        help='attribute {MF, SP, CC, AN, joint} (default: MF)')
    parser.add_argument('--use-all-data', action='store_true', default=False,
                        help='Use all data for final training (default: False)')
    parser.add_argument('--weight-sharing', action='store_true', default=False,
                        help='Use weight sharing (default: False)')
    parser.add_argument('--invariant', type=int, default=0.5, 
                        help='rate of invariant words for training (default: 0.5)')
    parser.add_argument('--batch-size', type=int, default=512, 
                        help='input batch size for training (default: 512)')
    parser.add_argument('--valid-batch-size', type=int, default=1000, 
                        help='input batch size for testing (default: 1000)')
    parser.add_argument('--epochs', type=int, default=100, 
                        help='number of epochs to train (default: 100)')
    parser.add_argument('--lr', type=float, default=0.0001, 
                        help='learning rate (default: 0.0001)')
    #parser.add_argument('--gamma', type=float, default=1.0, 
    #                    help='Learning rate step gamma (default: 1.0)')
    parser.add_argument('--dim-x', type=int, default=300, 
                        help='dim of word vectors (default: 300)')
    parser.add_argument('--dim-h', type=int, default=300, 
                        help='dim of hidden units (default: 300)')
    #parser.add_argument('--n-layers', type=int, default=5, 
    #                    help='num of layers (default: 5)')
    parser.add_argument('--sigma', type=float, default=0.1, 
                        help='gaussian noise standard deviation (default: 0.1)')
    parser.add_argument('--gpu', type=int, default=-1, 
                        help='gpu device id. -1 indicates cpu (default: -1)')
    parser.add_argument('--dry-run', action='store_true', default=False,
                        help='quickly check a single pass')
    parser.add_argument('--seed', type=int, default=1, 
                        help='random seed (default: 1)')
    parser.add_argument('--log-interval', type=int, default=10, 
                        help='how many batches to wait before logging training status')
    parser.add_argument('--fout', type=str, default='./result', 
                        help='output directory (default: ./result)')
    parser.add_argument('--save-model', action='store_true', default=False,
                        help='For Saving the current Model')
    args = parser.parse_args()
    print(json.dumps(args.__dict__, indent=2))
        
    torch.manual_seed(args.seed)
    device, use_cuda = utils.get_device(args.gpu)

    # Load dataset
    train_kwargs = {'batch_size': args.batch_size}
    valid_kwargs = {'batch_size': args.valid_batch_size}
    if use_cuda:
        cuda_kwargs = {'num_workers': 1,
                       'pin_memory': True,
                       'shuffle': True}
        train_kwargs.update(cuda_kwargs)
        valid_kwargs.update(cuda_kwargs)
    
    print('loading datasets...')
    if args.attr=='joint':
        attributes = ['MF', 'SP', 'CC', 'AN']
    else:
        attributes = [args.attr]
    dataset = utils.load_dataset(args.invariant, attributes, args.seed, args.emb)
    print('loaded.')
    
    # Create train/val/test data
    if args.use_all_data:
        X_train, T_train, Z_train = [], [], []
        for dtype, z, x, t in dataset:
            if type(t)==list:
                for target in t:
                    X_train.append(x)
                    T_train.append(target)
                    Z_train.append(ATTR2ID[z])
            else:
                X_train.append(x)
                T_train.append(t)
                Z_train.append(ATTR2ID[z])
        print('loading word embeddings...')
        word_embedding = utils.load_word_embeddings(args.emb)
        print('loaded.')
        print('creating data loader')
        X_train = torch.from_numpy(np.array([word_embedding[w] for w in X_train])).float()
        T_train = torch.from_numpy(np.array([word_embedding[w] for w in T_train])).float()
        Z_train = torch.from_numpy(np.array(Z_train))
        dataset1 = torch.utils.data.TensorDataset(X_train, T_train, Z_train)    
        train_loader = torch.utils.data.DataLoader(dataset1, **train_kwargs)
        print('created.')
    else:
        X_train = [d[2] for d in dataset if d[0]=='train']
        X_valid = [d[2] for d in dataset if d[0]=='valid']
        X_test = [d[2] for d in dataset if d[0]=='test']
        T_train = [d[3] for d in dataset if d[0]=='train']
        T_valid = [d[3] for d in dataset if d[0]=='valid']
        T_test = [d[3] for d in dataset if d[0]=='test']
        Z_train = [ATTR2ID[d[1]] for d in dataset if d[0]=='train']
        Z_valid = [ATTR2ID[d[1]] for d in dataset if d[0]=='valid']
        Z_test = [ATTR2ID[d[1]] for d in dataset if d[0]=='test']
    
        #assert len(X_valid) > 0
        #assert len(T_valid) > 0
        #assert len(Z_valid) > 0
    
        print('loading word embeddings...')
        word_embedding = utils.load_word_embeddings(args.emb)
        print('loaded.')
        
        print('creating data loader')
        X_train = torch.from_numpy(np.array([word_embedding[w] for w in X_train])).float()
        T_train = torch.from_numpy(np.array([word_embedding[w] for w in T_train])).float()
        Z_train = torch.from_numpy(np.array(Z_train))
        X_valid = torch.from_numpy(np.array([word_embedding[w] for w in X_valid])).float()
        T_valid = torch.from_numpy(np.array([word_embedding[w] for w in T_valid])).float()
        Z_valid = torch.from_numpy(np.array(Z_valid))
        X_test = torch.from_numpy(np.array([word_embedding[w] for w in X_test])).float()
        T_test = torch.from_numpy(np.array([word_embedding[w] for w in T_test])).float()
        Z_test = torch.from_numpy(np.array(Z_test))
        
        dataset1 = torch.utils.data.TensorDataset(X_train, T_train, Z_train)
        dataset2 = torch.utils.data.TensorDataset(X_valid, T_valid, Z_valid)
        dataset3 = torch.utils.data.TensorDataset(X_test, T_test, Z_test)
    
        train_loader = torch.utils.data.DataLoader(dataset1, **train_kwargs)
        valid_loader = torch.utils.data.DataLoader(dataset2, **valid_kwargs)
        test_loader = torch.utils.data.DataLoader(dataset3, **valid_kwargs)
        print('created.')
    
    # Set model
    if args.weight_sharing:
        model = Ref_PM_Share(args.dim_x, args.dim_h).to(device)
        args.model = 'Ref+PM+Share'
    else:
        model = Ref_PM(args.dim_x, args.dim_h).to(device)
        args.model = 'Ref+PM'
        
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    # Training
    #scheduler = StepLR(optimizer, step_size=1, gamma=args.gamma)
    training_loop = tqdm(range(1, args.epochs + 1))
    for epoch in training_loop:
        train_loss = train(args, model, device, train_loader, optimizer, epoch)
        if not args.use_all_data:
            valid_loss = test(model, device, valid_loader, 'Valid')
        else:
            valid_loss = -1.0
        training_loop.set_description("Train Epoch %d | Train Loss: %f | Valid Loss: %f" % (epoch, train_loss, valid_loss))
        #scheduler.step()
        if args.dry_run:
            break
            
    # Test
    if not args.use_all_data:
        test_loss = test(model, device, test_loader, 'Test')
        print('Test Loss: {:.6f}'.format(test_loss))

    # Save model
    if args.save_model:
        now = str(datetime.datetime.today()).replace(' ', '_').replace(':', '-').replace('.', '_')
        experiment_name = '{}_{}_{}_{}'.format(args.emb, args.attr, args.model, now)
        args.exp_name = experiment_name
        path_save = '{}/{}'.format(args.fout, experiment_name)
        os.makedirs(path_save, exist_ok=True)
        with open('{}/args.json'.format(path_save), 'w') as f:
            json.dump(args.__dict__, f)
        torch.save(model.state_dict(), "{}/model.pt".format(path_save))
        print('saved in ' + path_save)

        
if __name__ == '__main__':
    '''
        Example:
            $ python train.py --sigma 0.1 --save-model --attr MF
    '''
    main()