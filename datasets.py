import random
from collections import defaultdict
import numpy as np
import torch.utils.data
import torchvision.transforms as transforms
from torchvision.datasets import CIFAR10, MNIST, CelebA, FashionMNIST,CIFAR100
from data_loader import Lyme
from torch.utils.data import random_split


# fix random seed
random.seed(2023)
np.random.seed(2023)

def get_datasets(data_name, dataroot):
    """
    get_datasets returns train/val/test data splits of CIFAR10/100 datasets
    :param data_name: name of dataset, choose from [cifar10, cifar100]
    :param dataroot: root to data dir
    :param normalize: True/False to normalize the data
    :param val_size: validation split size (in #samples)
    :return: train_set, val_set, test_set (tuple of pytorch dataset/subset)
    """

    if data_name =='cifar':
        normalization = transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010))
        transform = transforms.Compose([transforms.ToTensor(), transforms.Resize((60, 32)), normalization])
        data_obj = CIFAR10
    elif data_name =='cifar100':
        normalization = transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
        transform = transforms.Compose([transforms.ToTensor(), transforms.Resize(224), normalization])
        data_obj = CIFAR100
    elif data_name == 'mnist':
        normalization = transforms.Normalize((0.1307,), (0.3081,))
        transform = transforms.Compose([transforms.ToTensor(),  normalization])
        data_obj = MNIST
    elif data_name == 'fmnist':
        normalization = transforms.Normalize((0.1307,), (0.3081,))
        transform = transforms.Compose([transforms.ToTensor(),  normalization])
        data_obj = FashionMNIST
    elif data_name == "lyme":
        normalization = transforms.Normalize(mean=[0.6579, 0.5389, 0.4849], std=[0.2591, 0.2434, 0.2491])
        transform = transforms.Compose([transforms.ToTensor(), transforms.Resize((224, 224)), normalization])
        data_obj = Lyme
    else:
        raise ValueError("choose data_name from ['mnist', 'cifar', 'fmnist']")

    train_set = data_obj(
        dataroot,
        download=True,
        train=True,
        transform=transform,
    )

    if data_name == "lyme":
        val_set = data_obj(
            dataroot,
            # download = True,
            train=False,
            val = True,
            transform=transform,
        )

    test_set = data_obj(
        dataroot,
        download = True,
        train=False,
        transform=transform,
    )

    # train_index = list(range(0, len(train_set), 10))
    # test_index  = list(range(0, len(test_set), 10))
    # train_set = torch.utils.data.Subset(train_set, train_index)
    # test_set = torch.utils.data.Subset(test_set, test_index)
    if data_name != "lyme":
        train_size = round(len(train_set) * 0.9)
        train_set, val_set = random_split(train_set, [train_size, len(train_set) - train_size])
    return train_set, val_set, test_set



def get_num_classes_samples(dataset):
    """
    extracts info about certain dataset
    :param dataset: pytorch dataset object
    :return: dataset info number of classes, number of samples, list of labels
    """
    # ---------------#
    # Extract labels #
    # ---------------#
    if isinstance(dataset, torch.utils.data.Subset):
        if isinstance(dataset.dataset.targets, list):
            data_labels_list = np.array(dataset.dataset.targets)[dataset.indices]
        else:
            data_labels_list = dataset.dataset.targets[dataset.indices]
    else:
        if isinstance(dataset.targets, list):
            data_labels_list = np.array(dataset.targets)
        else:
            data_labels_list = dataset.targets
    classes, num_samples = np.unique(data_labels_list, return_counts=True)
    num_classes = len(classes)
    return num_classes, num_samples, data_labels_list


def gen_classes_per_node(dataset, num_users, classes_per_user=2, high_prob=0.6, low_prob=0.4):
    # high_prob=0.6, low_prob=0.4
    """
    creates the data distribution of each client
    :param dataset: pytorch dataset object
    :param num_users: number of clients
    :param classes_per_user: number of classes assigned to each client
    :param high_prob: highest prob sampled
    :param low_prob: lowest prob sampled
    :return: dictionary mapping between classes and proportions, each entry refers to other client
    """
    num_classes, num_samples, _ = get_num_classes_samples(dataset)

    # -------------------------------------------#
    # Divide classes + num samples for each user #
    # -------------------------------------------#
    assert (classes_per_user * num_users) % num_classes == 0, "equal classes appearance is needed"
    count_per_class = (classes_per_user * num_users) // num_classes
    class_dict = {}
    for i in range(num_classes):
        # sampling alpha_i_c
        probs = np.random.uniform(low_prob, high_prob, size=count_per_class)
        # normalizing
        probs_norm = (probs / probs.sum()).tolist()
        class_dict[i] = {'count': count_per_class, 'prob': probs_norm}
    # -------------------------------------#
    # Assign each client with data indexes #
    # -------------------------------------#
    class_partitions = defaultdict(list)
    for i in range(num_users):
        c = []
        for _ in range(classes_per_user):
            class_counts = [class_dict[i]['count'] for i in range(num_classes)]
            max_class_counts = np.where(np.array(class_counts) == max(class_counts))[0]
            max_class_counts = np.setdiff1d(max_class_counts, np.array(c))
            c.append(np.random.choice(max_class_counts))
            class_dict[c[-1]]['count'] -= 1
        class_partitions['class'].append(c)
        class_partitions['prob'].append([class_dict[i]['prob'].pop() for i in c])
    return class_partitions


def gen_data_split(dataset, num_users, class_partitions):
    """
    divide data indexes for each client based on class_partition
    :param dataset: pytorch dataset object (train/val/test)
    :param num_users: number of clients
    :param class_partitions: proportion of classes per client
    :return: dictionary mapping client to its indexes
    """
    num_classes, num_samples, data_labels_list = get_num_classes_samples(dataset)
    # -------------------------- #
    # Create class index mapping #
    # -------------------------- #
    data_class_idx = {i: np.where(data_labels_list == i)[0] for i in range(num_classes)}

    # --------- #
    # Shuffling #
    # --------- #
    for data_idx in data_class_idx.values():
        random.shuffle(data_idx)

    # ------------------------------ #
    # Assigning samples to each user #
    # ------------------------------ #
    user_data_idx = [[] for i in range(num_users)]
    for usr_i in range(num_users):
        for c, p in zip(class_partitions['class'][usr_i], class_partitions['prob'][usr_i]):
            end_idx = int(num_samples[c] * p)
            user_data_idx[usr_i].extend(data_class_idx[c][:end_idx])
            data_class_idx[c] = data_class_idx[c][end_idx:]

    return user_data_idx


def gen_classes_id(num_users=10, num_classes_per_user=2, classes=10):
    class_partitions = defaultdict(list)
    class_counts = [list(range(classes)) for _ in range(num_classes_per_user)]
    user_data_classes = []
    for user in range(num_users):
        classes_user = np.random.choice(class_counts[0], size=1)
        class_counts[0].remove(classes_user[0])
        tmp = class_counts[1].copy()
        if classes_user[0] in tmp:tmp.remove(classes_user[0])
        if tmp is None:
            tmp=[user_data_classes[-1][0]]
            user_data_classes[-1][0] = classes_user[0]
        classes_user = np.append(classes_user, np.random.choice(tmp, size=1))
        class_counts[1].remove(classes_user[1])
        user_data_classes.append(classes_user)
    for c in user_data_classes:
        class_partitions['class'].append(c)
        class_partitions['prob'].append([0.5, 0.5])
    return class_partitions


def gen_classes(num_users=10, num_classes_per_user=6, classes=10):
    class_partitions = defaultdict(list)
    class_counts = [list(range(classes)) for _ in range(num_classes_per_user)]
    user_data_classes = []
    for user in range(num_users):
        user_data_classes.append(np.array([*range(user, user+num_classes_per_user)])%10)
    for c in user_data_classes:
        class_partitions['class'].append(c)
        class_partitions['prob'].append([1/num_classes_per_user]*num_classes_per_user)
    return class_partitions


def gen_random_loaders(data_name, data_path, num_users, bz, num_classes_per_user, num_classes, return_distributions=False):
    """
    generates train/val/test loaders of each client
    :param data_name: name of dataset, choose from [cifar10, cifar100]
    :param data_path: root path for data dir
    :param num_users: number of clients
    :param bz: batch size
    :param classes_per_user: number of classes assigned to each client
    :return: train/val/test loaders of each client, list of pytorch dataloaders
    """
    loader_params = {"batch_size": bz, "shuffle": False, "pin_memory": True, "num_workers": 0}
    dataloaders = []
    datasets = get_datasets(data_name, data_path)
    cls_partitions = None
    distribution = np.zeros((num_users, num_classes))
    for i, d in enumerate(datasets):
        # ensure same partition for train/test/val
        if i == 0:
            cls_partitions = gen_classes_per_node(d, num_users, num_classes_per_user)
            # cls_partitions = gen_classes_id()
            # cls_partitions = gen_classes(num_users=num_users, num_classes_per_user=num_classes_per_user, classes=classes)
            for index in range(num_users):
                distribution[index][cls_partitions['class'][index]] = cls_partitions['prob'][index]

            loader_params['shuffle'] = True
            # loader_params['drop_last'] = True
            print(cls_partitions)
        usr_subset_idx = gen_data_split(d, num_users, cls_partitions)
        subsets = list(map(lambda x: torch.utils.data.Subset(d, x), usr_subset_idx))
        # create dataloaders from subsets
        dataloaders.append(list(map(lambda x: torch.utils.data.DataLoader(x, **loader_params), subsets)))

        # dataloader_usr = []
        # for subset_idx in usr_subset_idx:
        #     # create subsets for each client
        #     subsets = list(map(lambda x: torch.utils.data.Subset(d, x), subset_idx))
        #     # create dataloaders from subsets
        #     dataloader_usr.append(list(map(lambda x: torch.utils.data.DataLoader(x, **loader_params), subsets)))
        # dataloaders.append(dataloader_usr)
    if return_distributions: dataloaders.append(distribution)
    return dataloaders