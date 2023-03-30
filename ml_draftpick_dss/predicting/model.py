from .util import sig_to_tanh_range, tanh_to_sig_range, split_dim
import torch
import torch
from torch import nn
import torch.nn.functional as F
from torch.nn import TransformerEncoder, TransformerEncoderLayer
from torch.nn import TransformerDecoder, TransformerDecoderLayer
import time
import tensorflow as tf
import numpy as np
from sklearn.metrics import accuracy_score, roc_auc_score, f1_score, confusion_matrix
from torchinfo import summary
import math


class NegativeSigmoid(torch.nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, x):
        return sig_to_tanh_range(torch.sigmoid(x))

class PositiveTanh(torch.nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, x):
        return tanh_to_sig_range(torch.tanh(x))

class NegativeBCELoss(torch.nn.BCELoss):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def forward(self, input, target):
        input = tanh_to_sig_range(input)
        target = tanh_to_sig_range(input)
        return super().forward(input, target)

MEAN = torch.mean
PROD = torch.prod
SUM = torch.sum
MAX = torch.max

class GlobalPooling1D(torch.nn.Module):
    def __init__(self, f=MEAN, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.f = f

    def forward(self, x):
        return self.f(x, dim=-2)
    
class PositionalEncoding(nn.Module):
    def __init__(self, d_model, dropout=0.1, max_len=5000):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        position = torch.arange(max_len).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2) * (-math.log(10000.0) / d_model))
        pe = torch.zeros(max_len, 1, d_model)
        pe[:, 0, 0::2] = torch.sin(position * div_term)
        pe[:, 0, 1::2] = torch.cos(position * div_term)
        self.register_buffer('pe', pe)

    def forward(self, x):
        """
        Args:
            x: Tensor, shape [seq_len, batch_size, embedding_dim]
        """
        x = x + self.pe[:x.size(0)]
        return self.dropout(x)

class ResultPredictorModel(nn.Module):

    def __init__(self, 
        d_model, 
        d_hid=128,
        nlayers=2,
        nhead=2,
        d_final=2,
        embedder=None,
        dropout=0.1,
        pooling=GlobalPooling1D,
        act_final=nn.ReLU,
        bidirectional=False,
        pos_encoder=True
    ):
        super().__init__()
        if embedder:
            d_model = embedder.dim
        else:
            embedder = nn.Identity()
        self.model_type = 'Transformer'
        self.bidirectional = bidirectional
        self.pos_encoder = PositionalEncoding(d_model, dropout) if pos_encoder else None
        encoder_layers = TransformerEncoderLayer(d_model, nhead, d_hid, dropout)
        decoder_layers = TransformerDecoderLayer(d_model, nhead, d_hid, dropout)
        self.d_model = d_model
        self.encoder = embedder
        self.transformer_encoder = TransformerEncoder(encoder_layers, nlayers)
        self.transformer_decoder = TransformerDecoder(decoder_layers, nlayers)
        self.pooling = pooling()

        final_dim = (2 if bidirectional else 1) * d_model
        if d_final == 0:
            self.decoder = nn.Identity()
        elif d_final == 1:
            self.decoder = nn.Sequential(
                *[
                    nn.Linear(final_dim, final_dim),
                    act_final()
                ]
            )
        else:
            self.decoder = nn.Sequential(
                *[
                    nn.Linear(final_dim, d_hid),
                    act_final(),
                    #nn.Dropout(dropout)
                ],
                *[
                    nn.Sequential(*[
                        nn.Linear(d_hid, d_hid),
                        act_final(),
                        nn.Dropout(dropout)
                    ])
                    for i in range(max(0, d_final-2))
                ],
                *[
                    nn.Linear(d_hid, final_dim),
                    act_final(),
                    #nn.Dropout(dropout)
                ],
            )
        self.victory_decoder = nn.Sequential(*[
            nn.Linear(final_dim, 1),
            nn.Sigmoid()
        ])
        self.score_decoder = nn.Sequential(*[
            nn.Linear(final_dim, 1),
            nn.Tanh()
        ])
        self.duration_decoder = nn.Sequential(*[
            nn.Linear(final_dim, 1),
            nn.Tanh()
        ])

        self.init_weights()
    
    def init_weights(self, layers=None, initrange=0.1):
        layers = layers or [
            self.decoder,
            self.victory_decoder,
            self.score_decoder,
            self.duration_decoder
        ]
        #self.encoder.weight.data.uniform_(-initrange, initrange)
        for layer in layers:
            if hasattr(layer, "__iter__"):
                self.init_weights(layer)
            else:
                if hasattr(layer, "bias"):
                    layer.bias.data.zero_()
                if hasattr(layer, "weight"):
                    layer.weight.data.uniform_(-initrange, initrange)
    
    def transform(self, src, tgt):
        memory = self.transformer_encoder(src)#, src_mask)
        tgt = self.transformer_decoder(tgt, memory)
        return tgt
    
    def pos_encode(self, x):
        if self.pos_encoder:
            x = x * math.sqrt(self.d_model)
            x = self.pos_encoder(x)
        return x

    def forward(self, left, right):
        left = self.encoder(left)
        left = self.pos_encoder(left)
        right = self.encoder(right)
        right = self.pos_encoder(right)
        
        if self.bidirectional:
            left = self.transform(left, right)
            right = self.transform(right, left)
            tgt = torch.cat([left, right], dim=-1)
        else:
            tgt = self.transform(left, right)

        tgt = self.pooling(tgt)
        tgt = self.decoder(tgt)
        victory = self.victory_decoder(tgt)
        score = self.score_decoder(tgt)
        duration = self.duration_decoder(tgt)
        output = victory, score, duration
        #output = torch.cat(output, dim=-1)
        return output
    
    def summary(self, batch_size=32, team_size=5, dim=6):
        return summary(
            self, 
            [(batch_size, team_size, dim) for i in range(2)], 
            dtypes=[torch.int, torch.int]
        )


class ResultPredictor:
    def __init__(
        self,
        d_model,
        *args,
        device=None,
        log_dir="logs",
        **kwargs
    ):
        device = device or torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = ResultPredictorModel(d_model, *args, **kwargs).to(device)
        self.epoch = 0
        self.training_prepared = False
        self.log_dir = log_dir
        self.file_writers = None

    def prepare_training(
            self,
            train_loader,
            val_loader=None,
            victory_crit=torch.nn.BCELoss,
            norm_crit=torch.nn.MSELoss,
            lr=1e-3,
            optimizer=torch.optim.SGD
        ):
        self.victory_crit = victory_crit()
        self.norm_crit = norm_crit()
        self.optimizer = optimizer(self.model.parameters(), lr=lr)
        self.scheduler = torch.optim.lr_scheduler.StepLR(self.optimizer, 1.0, gamma=0.95)
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.model.train()
        self.training_prepared = True

    def prepare_logging(self):
        self.file_writers = {
            "train": tf.summary.create_file_writer(self.log_dir + f"/train"),
            "val": tf.summary.create_file_writer(self.log_dir + f"/val"),
        }

    def train(self):
        assert self.training_prepared
        self.model.train()  # turn on train mode
        losses = {
            "total_victory_loss": 0, 
            "total_score_loss": 0, 
            "total_duration_loss": 0, 
            "total_loss": 0
        }
        start_time = time.time()

        batch_count = 0
        bin_true = []
        bin_pred = []
        min_victory_pred, max_victory_pred = 2, -2
        for i, batch in enumerate(self.train_loader):
            left, right, targets = batch
            victory_true, score_true, duration_true = split_dim(targets)
            victory_pred, score_pred, duration_pred = self.model(left, right)
            #victory_pred, norms_pred = preds[..., :1], preds[..., 1:]
            
            victory_loss = self.victory_crit(victory_pred, victory_true)
            score_loss = self.norm_crit(score_pred, score_true)
            duration_loss = self.norm_crit(duration_pred, duration_true)
            loss = victory_loss + score_loss + duration_loss

            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 0.5)
            self.optimizer.step()

            losses["total_victory_loss"] += victory_loss.item()
            losses["total_score_loss"] += score_loss.item()
            losses["total_duration_loss"] += duration_loss.item()
            losses["total_loss"] += loss.item()
            batch_count += 1
            min_victory_pred = min(min_victory_pred, torch.min(victory_pred).item())
            max_victory_pred = max(min_victory_pred, torch.max(victory_pred).item())
            bin_true.extend(list(torch.squeeze(victory_true, dim=-1) > 0))
            bin_pred.extend(list(torch.squeeze(victory_pred, dim=-1) > 0))

        bin_true, bin_pred = np.array(bin_true).astype(int), np.array(bin_pred).astype(int)
        cm = confusion_matrix(bin_true, bin_pred)
        cm_labels = ["tn", "fp", "fn", "tp"]

        losses = {k: v/batch_count for k, v in losses.items()}
        cur_metrics = {
            "epoch": self.epoch,
            **losses,
            "accuracy": accuracy_score(bin_true, bin_pred),
            "auc": roc_auc_score(bin_true, bin_pred),
            "f1": f1_score(bin_true, bin_pred),
            "min_victory_pred": min_victory_pred,
            "max_victory_pred": max_victory_pred,
            **{cm_labels[i]: x for i, x in enumerate(cm.ravel())}
        }
    
        lr = self.scheduler.get_last_lr()[0]
        ms_per_batch = (time.time() - start_time) * 1000 / batch_count
        print(f'| epoch {self.epoch:3d} | step {i:5d} | '
            f'lr {lr} | ms/batch {ms_per_batch:5.2f} | ')
        self.epoch += 1
        return cur_metrics
    
    def summary(self, *args, **kwargs):
        return self.model.summary(*args, **kwargs)