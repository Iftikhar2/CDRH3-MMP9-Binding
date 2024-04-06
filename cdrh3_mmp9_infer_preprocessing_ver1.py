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
  df_binding_AA_shuffled_list = list(df_test_ab_AA_shuffled.to_records(index=False))
  df_sequence_shuffled_list= df_test_ab_shuffled['Full_AA_Sequence'].tolist()

  return df_test_ab_shuffled, df_shuffled_list, df_binding_AA_shuffled_list, df_sequence_shuffled_list

def representations_650MB(df_shuffled_list,df_binding_AA_shuffled_list):

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
  no_steps= int(len(df_binding_AA_shuffled_list)/batch_size)

  for i in range(no_steps+1):
    #setting the lower and upper boundaries for the batch
    lower= i*batch_size
    upper= lower+batch_size
    upper=upper if upper<len(df_binding_AA_shuffled_list) else len(df_binding_AA_shuffled_list)
    print(f"lower:{lower},upper:{upper}")

    #Creating the amino acid and sample data lists for the batch based on the lower and upper boundaries
    AA_data=[df_binding_AA_shuffled_list[i] for i in range(lower,upper)]
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
  #The max_CDRH3 length in the training file is 17. Hence hardcoded here.
  max_CDRH3_length = 17
  for i in range(len(embedding_list_650MB)):
    number_of_padding_required = max_CDRH3_length - len(embedding_list_650MB[i])
    for j in range(number_of_padding_required):
      seq_rep_padded_650MB[i] = pad(seq_rep_padded_650MB[i])

  test_ab_650MB_array=np.array([seq_rep_padded_650MB[i].cpu().numpy() for i in range(len(seq_rep_padded_650MB))] )

  return test_ab_650MB_array

def representations_3B(df_shuffled_list,df_binding_AA_shuffled_list):

    import torch
    import esm
    
    # Load ESM-2 model
    #model, alphabet = esm.pretrained.esm2_t33_650M_UR50D()
    esm2_3B, alphabet1 = esm.pretrained.esm2_t36_3B_UR50D()
    #model, alphabet = esm.pretrained.esm2_t48_15B_UR50D()
    
    import torch
    torch.cuda.empty_cache()
    
    # Load ESM-2 model
    #model, alphabet = esm.pretrained.esm2_t33_650M_UR50D()
    #model1, alphabet1 = esm.pretrained.esm2_t36_3B_UR50D()
    #model, alphabet = esm.pretrained.esm2_t48_15B_UR50D()
    device = torch.device("cuda")
    esm2_3B = esm2_3B.eval().cuda()
    esm2_3B.to(device)
    batch_converter1 = alphabet1.get_batch_converter()
    
    #Creating batches to avoid any out of memory error
    #model.eval()  # disables dropout for deterministic results

    seq_rep_aa_in_cdrh3_average_3B = []
    batch_size=200
    
    no_steps= int(len(df_binding_AA_shuffled_list)/batch_size)
    for i in range(no_steps+1):
      #setting the lower and upper boundaries for the batch
      lower= i*batch_size
      upper= lower+batch_size
      upper=upper if upper<len(df_binding_AA_shuffled_list) else len(df_binding_AA_shuffled_list)
      print(f"lower:{lower},upper:{upper}")
    
     #Creating the amino acid and sample data lists for the batch based on the lower and upper boundaries
      AA_data=[df_binding_AA_shuffled_list[i] for i in range(lower,upper)]
      batch_data = [df_shuffled_list[i] for i in range(lower,upper)]
    
      batch_labels, batch_strs, batch_tokens = batch_converter1(AA_data)
      #batch_lens = (batch_tokens != alphabet.padding_idx).sum(1)
      #print(batch_lens)
    
      #print(batch_strs)
      #print(batch_labels)
      #print(batch_tokens)
    
      batch_tokens = batch_tokens.to(next(esm2_3B.parameters()).device)
    
      with torch.no_grad():
        results = esm2_3B(batch_tokens, repr_layers=[33], return_contacts=False)
        token_representations = results["representations"][33]
       #print(token_representations)
    
      # Generate CDRH3 per-sequence representations via averaging over CDRH3
    
      for i, (_, _, _, _, _, start_idx, cdrh3_len ) in enumerate(batch_data):
       # NOTE: token 0 is always a beginning-of-sequence token, so the first residue is token 1. It means that we need to add 1 to CDRH3 start index.
        for j in range(cdrh3_len):
          if (j==0):
            seq_rep = []
          seq_rep.append(token_representations[i, start_idx+j+1: (start_idx + j + 2)].mean(0).cpu())
        seq_rep_aa_in_cdrh3_average_3B.append(seq_rep)

    embedding_list_3B = []
    for i in range(len(seq_rep_aa_in_cdrh3_average_3B)):
      embedding_list_3B.append(torch.stack((seq_rep_aa_in_cdrh3_average_3B[i])))

    seq_rep_padded_3B = embedding_list_3B.copy()
    
    import torch
    import torch.nn as nn
    padding = (0,0,0,1)
    pad = nn.ZeroPad2d(padding)
    #max_CDRH3_length = 10
    #The max_CDRH3 length in the training file is 17. Hence hardcoded here.
    max_CDRH3_length = 17
    for i in range(len(embedding_list_3B)):
      number_of_padding_required = max_CDRH3_length - len(embedding_list_3B[i])
      for j in range(number_of_padding_required):
        seq_rep_padded_3B[i] = pad(seq_rep_padded_3B[i])
    
    test_ab_3B_array=np.array([seq_rep_padded_3B[i].cpu().numpy() for i in range(len(seq_rep_padded_3B))] )
    
    return test_ab_3B_array

def representations_15B(df_shuffled_list,df_sequence_shuffled_list):

    import transformers
    checkpoint = "Rocketknight1/esm2_t48_15B_UR50D"
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    
    import torch
    torch.cuda.empty_cache()
    
    import torch
    from transformers import pipeline
    
    esm_feature_extractor = pipeline(task="feature-extraction",framework="pt",model=checkpoint, tokenizer=tokenizer, device='cuda', torch_dtype=torch.bfloat16)

    seq_rep_avg_aa_in_cdrh3_15B = []
    batch_size=200
    #Ifthi: Modified this for test ab
    #df_AA_Sequences_List = list(df_shuffled['Full_AA_Sequence'])
    #df_AA_Sequences_List = list(df_test_ab_shuffled['Full_AA_Sequence'])
    
    no_steps= int(len(df_sequence_shuffled_list)/batch_size)
    for i in range(no_steps+1):
      #setting the lower and upper boundaries for the batch
      lower= i*batch_size
      upper= lower+batch_size
      upper=upper if upper<len(df_sequence_shuffled_list) else len(df_sequence_shuffled_list)
      print(f"lower:{lower},upper:{upper}")
    
      #Creating the amino acid and sample data lists for the batch based on the lower and upper boundaries
      AA_data=[df_sequence_shuffled_list[i] for i in range(lower,upper)]
      batch_data = [df_shuffled_list[i] for i in range(lower,upper)]
    
      with torch.autocast("cuda"):
        features1=esm_feature_extractor(AA_data,return_tensors = "pt")
    
      # Generate CDRH3 per-sequence representations via averaging over CDRH3
      for i, (_, _, _, _, _, start_idx, cdrh3_len ) in enumerate(batch_data):
       # NOTE: token 0 is always a beginning-of-sequence token, so the first residue is token 1. It means that we need to add 1 to CDRH3 start index.
       # Similarly, since we have to take average over CDRH3, we need to add 1 to CDRH3 length to mark the end of slcing in the tensor.
       #sequence_representations6.append(features1[i][0,(start_idx+1):(start_idx + 1 + cdrh3_len + 1)].mean(0))
       #sequence_representations6.append(features1[i][0,(start_idx+1):(start_idx + 1 + cdrh3_len)].mean(0))
        for j in range(cdrh3_len):
          if (j==0):
            seq_rep = []
          #embedding_tensor_stack = token_representations[i, start_idx+j+1: (start_idx + j + 2)].mean(0).cpu
        #sequence_representations_650MB.append(token_representations[i][(start_idx+j+1): (start_idx + j+ 2)].mean(0))
        #seq_rep.append(token_representations[i, start_idx+j+1: (start_idx + j + 2)].mean(0))
        #seq_rep.append(token_representations[i, start_idx+j+1: (start_idx + j + 2)].mean(0).cpu())
          seq_rep.append(features1[i][0,(start_idx+j+1):(start_idx + j+2)].mean(0).cpu())
        seq_rep_avg_aa_in_cdrh3_15B.append(seq_rep)

    embedding_list_15B = []
    for i in range(len(seq_rep_avg_aa_in_cdrh3_15B)):
      embedding_list_15B.append(torch.stack((seq_rep_avg_aa_in_cdrh3_15B[i])))

    seq_rep_padded_15B = embedding_list_15B.copy()
    
    import torch
    import torch.nn as nn
    padding = (0,0,0,1)
    pad = nn.ZeroPad2d(padding)
    #max_CDRH3_length = 10
    #The max_CDRH3 length in the training file is 17. Hence hardcoded here.
    max_CDRH3_length = 17
    for i in range(len(embedding_list_15B)):
      number_of_padding_required = max_CDRH3_length - len(embedding_list_15B[i])
      for j in range(number_of_padding_required):
        seq_rep_padded_15B[i] = pad(seq_rep_padded_15B[i])
    
    test_ab_15B_array=np.array([seq_rep_padded_15B[i].cpu().numpy() for i in range(len(seq_rep_padded_15B))] )
    
    return test_ab_15B_array

def antiberty_representations(df_shuffled_list,df_sequence_shuffled_list):

    from antiberty import AntiBERTyRunner

    antiberty = AntiBERTyRunner()

    sequence_representations_antiberty = []
    batch_size=200
    no_steps= int(len(df_sequence_shuffled_list)/batch_size)
    
    for i in range(no_steps+1):
      #setting the lower and upper boundaries for the batch
      lower= i*batch_size
      upper= lower+batch_size
      upper=upper if upper<len(df_sequence_shuffled_list) else len(df_sequence_shuffled_list)
      print(f"lower:{lower},upper:{upper}")
    
      #Creating the amino acid and sample data lists for the batch based on the lower and upper boundaries
      AA_data=[df_sequence_shuffled_list[i] for i in range(lower,upper)]
      batch_data = [df_shuffled_list[i] for i in range(lower,upper)]
      #batch_labels, batch_strs, batch_tokens = batch_converter(AA_data)
      embeddings = antiberty.embed(AA_data)
      #print(embeddings)
      #batch_lens = (batch_tokens != alphabet.padding_idx).sum(1)
      #print(batch_lens)
    
      #print(batch_strs)
      #print(batch_labels)
      #print(batch_tokens)
    
    
      embeddings_cpu=[embeddings[i].cpu() for i in range(len(embeddings))]
      # Generate  per-sequence GDRH3 representations
      for i, (_, _, _, _, _, start_idx, cdrh3_len ) in enumerate(batch_data):
       # NOTE: token 0 is always a beginning-of-sequence token, so the first residue is token 1. It means that we need to add 1 to CDRH3 start index.
       sequence_representations_antiberty.append(embeddings_cpu[i][start_idx+1: (start_idx + 1 + cdrh3_len)])

    antiberty_seq_rep_padded = sequence_representations_antiberty.copy()
    
    import torch
    import torch.nn as nn
    padding = (0,0,0,1)
    pad = nn.ZeroPad2d(padding)
    #max_CDRH3_length = 10
    #The max_CDRH3 length in the training file is 17. Hence hardcoded here.
    max_CDRH3_length = 17
    for i in range(len(sequence_representations_antiberty)):
      number_of_padding_required = max_CDRH3_length - len(sequence_representations_antiberty[i])
      for j in range(number_of_padding_required):
        antiberty_seq_rep_padded[i] = pad(antiberty_seq_rep_padded[i])
    
    test_ab_antiberty_array=np.array([antiberty_seq_rep_padded[i].cpu().numpy() for i in range(len(antiberty_seq_rep_padded))] )
    
    return test_ab_antiberty_array

def infer(df_test_ab,model):

  df_test_ab_shuffled, df_shuffled_list, df_binding_AA_shuffled_list, df_sequence_shuffled_list = infer_preprocessing(df_test_ab)

  #lstm_model_650MB = keras.models.load_model("drive/MyDrive/Protein_Engineering_Project/lstm_650MB_run1_SHAP_Mask_revised_mmp9_030824")
  if model == 'ESM2 650MB':
      lstm_model = keras.models.load_model("/content/CDRH3-MMP9-Binding/saved-representations-and-models/lstm_650MB_run1_SHAP_Mask_revised_mmp9_030824")
      test_ab_array = representations_650MB(df_shuffled_list,df_binding_AA_shuffled_list)
  elif model == 'ESM2 3B':
      lstm_model = keras.models.load_model("/content/CDRH3-MMP9-Binding/saved-representations-and-models/lstm_3B_run1_SHAP_revised_mmp9_030824")
      test_ab_array = representations_3B(df_shuffled_list,df_binding_AA_shuffled_list)
  elif model == 'ESM2 15B':
      lstm_model = keras.models.load_model("/content/CDRH3-MMP9-Binding/saved-representations-and-models/lstm_15B_SHAP_run1_revised_mmp9_030824")
      test_ab_array = representations_15B(df_shuffled_list,df_sequence_shuffled_list)
  else:
      lstm_model = keras.models.load_model("/content/CDRH3-MMP9-Binding/saved-representations-and-models/lstm_antiberty_run1_SHAP_Mask_revised_mmp9_030824")
      test_ab_array = antiberty_representations(df_shuffled_list,df_sequence_shuffled_list)
  
  y_pred = lstm_model.predict(test_ab_array, verbose=1)

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
