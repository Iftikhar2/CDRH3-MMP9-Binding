# -*- coding: utf-8 -*-
"""CDRH3_MMP9_infer_preprocessing_ver1.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1EUYK4LQAmeM7k2UkqeY0tmG7KicvXogg

## Installing transormers and required libraries
"""

#!pip install transformers
#!pip install fair-esm
#!pip install keras-tuner --upgrade

import pandas as pd
import numpy as np
import csv
import tensorflow as tf
from tensorflow import keras

#from google.colab import drive
#drive.mount('/content/drive')

"""# Creating represenations and predictions for test ab vs MMP-9 sent by Masoud

Ifthi: Test_Ab file from Masoud
"""

def infer_preprocessing(df_test_ab):

  #The max_CDRH3 length in the training file is 17. Hence hardcoded here.
  max_CDRH3_length = 17

  #Ifthi: Preses command+curly braces to indent blocks of code
  #Creating new column 'Binding' containing affinity labels
  #ifthi adding dummy binding and binding labels. Not actual ones just to keep the input file in the same format as the original ones used for training.
  df_test_ab["Binding"] = "Positive"
  df_test_ab["Binding_Labels"] = 1
  #df_test_ab["Count"] = 1


  #Creating a new column 'CDRH3_Length' to store the length of CDRH3 to be used in CDRH3 per-sequence averaging
  df_test_ab['CDRH3_Length'] = df_test_ab['CDRH3'].str.len()

  #Creating a new column 'Start_Idx' to store the starting index of the given CDRH3 in the full amino acid sequence to be used in CDRH3 per-sequence averaging
  df_test_ab['Start_Idx'] = 0

  #Creating a new column 'CDRH3_Length' to store the length of CDRH3 to be used in CDRH3 per-sequence averaging
  df_test_ab['Full_AA_Sequence'] = df_test_ab['CDRH3']

  print("Total number of test sequences with CDRH3: ", len(df_test_ab[(df_test_ab['Binding_Labels'] == 1)]))

  df_test_ab_Binding_AA = df_test_ab[['Binding','Binding_Labels', 'Full_AA_Sequence','Count','CDRH3','Start_Idx', 'CDRH3_Length']]

  df_test_ab_shuffled = df_test_ab_Binding_AA.sample(frac=1,random_state=200)

  df_shuffled_list = list(df_test_ab_shuffled.to_records(index=False))

  df_test_ab_AA_shuffled= df_test_ab_shuffled[['Binding', 'Full_AA_Sequence']]
  df_AA_shuffled_list = list(df_test_ab_AA_shuffled.to_records(index=False))

  import torch
  import esm

  # Load ESM-2 model
  model, alphabet = esm.pretrained.esm2_t33_650M_UR50D()
  #model, alphabet = esm.pretrained.esm2_t36_3B_UR50D()
  #model, alphabet = esm.pretrained.esm2_t48_15B_UR50D()
  device = torch.device("cuda")
  model = model.eval().cuda()
  model.to(device)
  batch_converter = alphabet.get_batch_converter()

  sequence_representations_650MB = []

  batch_size=200
  no_steps= int(len(df_AA_shuffled_list)/batch_size)

  for i in range(no_steps+1):
    #setting the lower and upper boundaries for the batch
    lower= i*batch_size
    upper= lower+batch_size
    upper=upper if upper<len(df_AA_shuffled_list) else len(df_AA_shuffled_list)
    print(f"lower:{lower},upper:{upper}")

    #Creating the amino acid and sample data lists for the batch based on the lower and upper boundaries
    AA_data=[df_AA_shuffled_list[i] for i in range(lower,upper)]
    batch_data = [df_shuffled_list[i] for i in range(lower,upper)]
    batch_labels, batch_strs, batch_tokens = batch_converter(AA_data)
    #batch_lens = (batch_tokens != alphabet.padding_idx).sum(1)
    #print(batch_lens)

    #print(batch_strs)
    #print(batch_labels)
    #print(batch_tokens)

    batch_tokens = batch_tokens.to(next(model.parameters()).device)

    with torch.no_grad():
      results = model(batch_tokens, repr_layers=[33], return_contacts=False)
      token_representations = results["representations"][33]
      #print(token_representations)

    # Generate CDRH3 per-sequence representations via averaging over CDRH3
    for i, (_, _, _, _, _, start_idx, cdrh3_len ) in enumerate(batch_data):
    # NOTE: token 0 is always a beginning-of-sequence token, so the first residue is token 1. It means that we need to add 1 to CDRH3 start index.
    #sequence_representations1.append(token_representations[i, start_idx+1: (start_idx + 1 + cdrh3_len)].mean(0))
    #Get the each aa in CDRH3 and get the average token representations for that aminoacid
      for j in range(cdrh3_len):
        if (j==0):
          #Initializing for each CDRH3
          seq_rep = []
        seq_rep.append(token_representations[i, start_idx+j+1: (start_idx + j + 2)].mean(0).cpu())
      #torch.stack((tensor_stack,T1))
      sequence_representations_650MB.append(seq_rep)

    #Since each aminoacid in CDRH3 has a separate tesnsor, we need to stack them together to create sequence of tensors for a given CDRH3.

  embedding_list_650MB = []

  for i in range(len(sequence_representations_650MB)):
    embedding_list_650MB.append(torch.stack((sequence_representations_650MB[i])))

  #Padding sequences to the maximum CDRH3 length to make all the embeddings' length equal

  seq_rep_padded_650MB = embedding_list_650MB.copy()

  import torch
  import torch.nn as nn
  padding = (0,0,0,1)
  pad = nn.ZeroPad2d(padding)
  #max_CDRH3_length = 10
  for i in range(len(embedding_list_650MB)):
    number_of_padding_required = max_CDRH3_length - len(embedding_list_650MB[i])
    for j in range(number_of_padding_required):
      seq_rep_padded_650MB[i] = pad(seq_rep_padded_650MB[i])

  test_ab_650MB_array=np.array([seq_rep_padded_650MB[i].cpu().numpy() for i in range(len(seq_rep_padded_650MB))] )

  return test_ab_650MB_array,df_test_ab_shuffled

def infer(df_test_ab):

  test_ab_650MB_array, df_test_ab_shuffled = infer_preprocessing(df_test_ab)

  lstm_model_650MB = keras.models.load_model("drive/MyDrive/Protein_Engineering_Project/lstm_650MB_run1_SHAP_Mask_revised_mmp9_030824")

  y_pred = lstm_model_650MB.predict(test_ab_650MB_array, verbose=1)

  predictions = ['Positive' if i > 0.5 else 'Negative' for i in y_pred]

  confidence = [i*100 for i in y_pred]

  result = pd.DataFrame()
  result["CDRH3"] = df_test_ab_shuffled['CDRH3']
  result['prediction'] = predictions
  result['confidence'] = confidence

  return result

#Create Positive and Negative binding data frames from cleaned csv files
#df_test_ab = pd.read_csv("drive/MyDrive/Protein_Engineering_Project/Test_Ab_vs_MMP9_from_Masoud.csv")
#print("Total test sequences: ", len(df_test_ab))

#inference = infer(df_test_ab)

#inference.head()
