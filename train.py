import time
import datetime
import pytz  

import numpy as np
import torch 
import torch.nn as nn
import torch.nn.functional as F
import torchvision.utils as vutils # contains useful functions like make_grid
from torch.utils.tensorboard import SummaryWriter
import wandb


from model.net import DenseDepth, evaluate_predictions, combined_loss 
from model.dataloader import DataLoaders
from utils import *
from evaluate import evaluate

# shift these to config files or inside the class later
DATA_PATH = 'nyu_data.zip'
NUM_EPOCHS = 9
LEARNING_RATE = 1e-4


class Trainer():
  def __init__(self, data_path = DATA_PATH):
    self.dataloaders = DataLoaders(data_path)  

  def train_and_evaluate(self, batch_size, checkpoint_file = None):
    """
    TODO: log other values/images
    """
    device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')

    train_dataloader = self.dataloaders.get_train_dataloader(batch_size = batch_size) # provide val batch size also
    num_batches = len(train_dataloader)

    model = DenseDepth()
    model = model.to(device)
    
    optimizer = torch.optim.Adam(model.parameters(), LEARNING_RATE)
    lr_scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size = 5, gamma = 0.1)

    wandb.watch(model, log="all")

    if checkpoint_file:
      load_checkpoint(checkpoint_file, model, optimizer)

    model.train()

    writer = SummaryWriter(comment = 'densenet121-bs-{}-lr-{}-epochs-{}'.format(batch_size, LEARNING_RATE, NUM_EPOCHS), flush_secs = 30)

    best_rmse = 9e20
    is_best = False
    best_test_rmse = 9e20
    is_best_test = False

    for epoch in range(NUM_EPOCHS):
      
      accumulated_loss = RunningAverage()
      accumulated_iteration_time = RunningAverage()
      epoch_start_time = time.time()

      for iteration, batch in enumerate(train_dataloader):

        time_start = time.time()        

        optimizer.zero_grad()
        images, depths = batch['img'], batch['depth']
        images = torch.autograd.Variable(images.to(device))
        depths = torch.autograd.Variable(depths.to(device))

        # depths = 1000.0/depths

        predictions = model(images)

        loss = combined_loss(predictions, depths)
        accumulated_loss.update(loss, images.shape[0])

        loss.backward()
        optimizer.step()

        time_end = time.time()
        accumulated_iteration_time.update(time_end - time_start)
        eta = str(datetime.timedelta(seconds = int(accumulated_iteration_time() * (num_batches - iteration))))


        net_iteration_number = epoch * num_batches + iteration

        if iteration % 10 == 0: 
          wandb.log({'Training loss': loss.item()})
          # writer.add_scalar('Training loss wrt iterations',loss, net_iteration_number)

        if iteration % 50 == 0:

          
          # writer.add_text('eta',eta, net_iteration_number)
          # writer.add_text('loss',str(loss.item()), net_iteration_number)
          # writer.add_text('avg loss',str(accumulated_loss().item()), net_iteration_number)

          print('Epoch: %d [%d / %d] ; it_time: %f (%f) ; eta: %s ; loss: %f (%f)' % (epoch, iteration, num_batches, time_end - time_start, accumulated_iteration_time(), eta, loss.item(), accumulated_loss()))
          metrics = evaluate_predictions(predictions, depths)
          self.write_metrics(metrics,train = True)

          test_images, test_depths, test_preds, test_loss, test_metrics = evaluate(model, self.dataloaders.get_val_dataloader, batch_size = 2) ; model.train() # evaluate(in model.eval()) and back to train
          # self.compare_predictions(test_images, test_depths, test_preds)
          wandb.log({'Validation loss on random batch':test_loss.item()})
          self.write_metrics(test_metrics, train = False)

          if metrics['rmse'] < best_rmse: 
            best_rmse = metrics['rmse']
            is_best = True

          save_checkpoint({'iteration':net_iteration_number, 
                          'state_dict': model.state_dict(), 
                          'optim_dict': optimizer.state_dict()},
                          is_best = is_best,
                          checkpoint_dir = 'experiments/train')

          if test_metrics['rmse'] < best_test_rmse: 
            best_test_rmse = test_metrics['rmse']
            is_best_test = True

          save_checkpoint({'iteration':net_iteration_number, 
                          'state_dict': model.state_dict(), 
                          'optim_dict': optimizer.state_dict()},
                          is_best = is_best_test,
                          checkpoint_dir = 'experiments/test') 

          is_best_test = False
          is_best = False

        print(datetime.datetime.now(pytz.timezone('Asia/Kolkata')), end = ' ')
        print('Epoch %d[%d/%d] complete' % (epoch, iteration, num_batches))

                               

      epoch_end_time = time.time()
      print('Epoch %d complete, time taken: %s' % (epoch, str(datetime.timedelta(seconds = int(epoch_end_time - epoch_start_time)))))
      wandb.log({'Average Training loss across epochs': accumulated_loss().item()}) 
      lr_scheduler.step() 
      
     


  def write_metrics(self, metrics, train = True):
    if train:
      for key, value in metrics.items():
        wandb.log({'Train '+key: value})
    else:
      for key, value in metrics.items():
        wandb.log({'Validation '+key: value}) 


  # def compare_predictions(self, images, depths, predictions):
  # # Plots the image on Tensorboard along with its true depth and prediction depths, and the L1 loss image

  #   vis_depths = depths/1000 * 255
  #   vis_preds = predictions/1000 * 255
  #   writer.add_image('Image', vutils.make_grid(images, nrow = 2), net_iteration_number)
  #   writer.add_image('True depth', vutils.make_grid(vis_depths, nrow = 2), net_iteration_number)
  #   writer.add_image('Predicted depth', vutils.make_grid(vis_preds, nrow = 2), net_iteration_number)
  #   writer.add_image('L1 loss', vutils.make_grid(torch.abs(vis_depths - vis_depths), nrow = 2), net_iteration_number)


