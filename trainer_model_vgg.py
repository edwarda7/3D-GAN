import os
import glob
import time
import numpy as np
import torch
import torch.utils
import torch.nn as nn
import torchvision
from torch.autograd import Variable
from torch.utils.data import DataLoader


from dataset import VaganDataset,LRWdataset
from model_vgg import Generator
from tensorboard_logger import configure, log_value

class Trainer():
    def __init__(self, config):
        self.generator = Generator()

        print(self.generator)
        self.l1_loss_fn =  nn.L1Loss()
        # self.l1_loss_fn =  nn.MSELoss()
        self.opt_g = torch.optim.Adam(self.generator.parameters(),
            lr=config.lr, betas=(config.beta1, config.beta2))
        

        if config.dataset == 'grid':
            self.dataset = VaganDataset(config.dataset_dir, train=config.is_train)
        elif config.dataset == 'lrw':
            self.dataset = LRWdataset(config.dataset_dir, train=config.is_train)
    
        self.data_loader = DataLoader(self.dataset,
                                      batch_size=config.batch_size,
                                      num_workers=12,
                                      shuffle=True, drop_last=True)
        data_iter = iter(self.data_loader)
        data_iter.next()
        self.ones = Variable(torch.ones(config.batch_size), requires_grad=False)
        self.zeros = Variable(torch.zeros(config.batch_size), requires_grad=False)

        if config.cuda:

            device_ids = [int(i) for i in config.device_ids.split(',')]
            self.generator     = nn.DataParallel(self.generator.cuda(), device_ids=device_ids)
            self.l1_loss_fn = self.l1_loss_fn.cuda()
            self.ones          = self.ones.cuda()
            self.zeros         = self.zeros.cuda()

        self.config = config
        self.start_epoch = 0

    def fit(self):
        config = self.config
        configure("{}/".format(config.log_dir), flush_secs=5)
        num_steps_per_epoch = len(self.data_loader)
        cc  = 0 
        for epoch in range(self.start_epoch, config.max_epochs):
            for step, (example, real_im, landmarks, right_audio, wrong_audio) in enumerate(self.data_loader):
                t1 = time.time()

                if config.cuda:
                    example = Variable(example).cuda()
                    landmarks = Variable(landmarks).cuda()
                    real_im    = Variable(real_im).cuda()
                    right_audio = Variable(right_audio).cuda()
                    wrong_audio = Variable(wrong_audio).cuda()
                else:
                    example = Variable(example)
                    landmarks = Variable(landmarks)
                    real_im    = Variable(real_im)
                    right_audio = Variable(right_audio)
                    wrong_audio = Variable(wrong_audio)

                # generate fake image
                # noise = Variable(torch.randn(config.batch_size, config.noise_size))
                # noise = noise.cuda() if config.cuda else noise
                fake_im = self.generator(example, right_audio)


                loss_gen = self.l1_loss_fn(fake_im,real_im)

                loss_gen.backward()
                self.opt_g.step()
                self._reset_gradients()

                t2 = time.time()

                if (step+1) % 1 == 0 or (step+1) == num_steps_per_epoch:
                    steps_remain = num_steps_per_epoch-step+1 + \
                        (config.max_epochs-epoch+1)*num_steps_per_epoch
                    eta = int((t2-t1)*steps_remain)

                    print("[{}/{}][{}/{}]   Loss_G: {:.4f} ,  ETA: {} second"
                          .format(epoch+1, config.max_epochs,
                                  step+1, num_steps_per_epoch, loss_gen.data[0],  eta))
                    log_value('generator_loss',loss_gen.data[0] , step + num_steps_per_epoch * epoch)
                if (step ) % (num_steps_per_epoch/3) == 0 :
                    fake_store = fake_im.data.permute(0,2,1,3,4).contiguous().view(config.batch_size*16,3,64,64)
                    torchvision.utils.save_image(fake_store, 
                        "{}fake_{}.png".format(config.sample_dir,cc), nrow=16,normalize=True)
                    real_store = real_im.data.permute(0,2,1,3,4).contiguous().view(config.batch_size*16,3,64,64)
                    torchvision.utils.save_image(real_store,
                        "{}real_{}.png".format(config.sample_dir,cc), nrow=16,normalize=True)
                    cc += 1
            if epoch % 1 == 0:
                torch.save(self.generator.state_dict(),
                           "{}/generator_{}.pth"
                           .format(config.model_dir,epoch))

    def load(self, directory):
        paths = glob.glob(os.path.join(directory, "*.pth"))
        gen_path  = [path for path in paths if "generator" in path][0]


        self.generator.load_state_dict(torch.load(gen_path))

        self.start_epoch = int(gen_path.split(".")[0].split("_")[-1])
        print("Load pretrained [{}, {},{}]".format(gen_path, disc_path,diff_path))

    def _reset_gradients(self):
        self.generator.zero_grad()
