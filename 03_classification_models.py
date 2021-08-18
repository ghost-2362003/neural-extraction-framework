'''
03 Classification Models

This code aims to train classification models to recognize the causality sentences from wikipages

* Input: The semEval dataframes
* Approaches: get the sentence embeddings to train on the *Logistic Regression* classifier; apply the *LSTM classifier* with specific sentence embedding techniques
* Output: Evaluate the models with different metrics'''


### import and install necessary packages

import os
import re
import random
import glob
import copy
import sys

import pandas as pd
import numpy as np

import time

import pickle 

from collections import Counter

import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)


from gensim.test.utils import common_texts
from gensim.models.doc2vec import Doc2Vec, TaggedDocument  # sentece to vec

from sklearn import metrics # for evaluation
from sklearn.linear_model import LogisticRegression # classifer

import spacy
nlp= spacy.load('en_core_web_sm') # tokenized sentence

path_here = os.getcwd()

# to install if you don't install yet
# !{sys.executable} -m pip install tensorflow
from tf_model_03 import get_model, get_feature_arrays
from utils_03 import get_n_epochs


#----------------------------------functions----------------------------------#


### purpose: get the embedding of the subset sentences 
### input: df_subset, the trained whole model
### output: the embedding feature space
def GetEmb(df_subset, model):

    wv_doc2vec = []
    for inx in df_subset.index.tolist():
        wv_doc2vec.append(model.dv[inx])
    return np.array(wv_doc2vec)
    
    

### purpose: to find the index of NPs pairs in sentences
### input: The SemEval Dataframe
### output: The SemEval Dataframe with 3 more columns <'ele1_word_idx', 'ele2_word_idx', 'tokens'>

def addInxcolDf(df_train_filtered):
    # be aware it will be the new dataframe
    new_list = df_train_filtered.columns.to_list()
    t_list = ['ele1_word_idx', 'ele2_word_idx', 'tokens']
    new_list.extend(t_list)
    df = pd.DataFrame(columns = new_list)
    
    # find index of all tokens in one NP 
    def findInx(tokens):
        ls = ['Cause', 'Effect']
        res = []
        for v in ls: 
            ele_A = re.findall(r"[\w']+|[.,!?;-]", rows[v])
            try: 
                inx_l = tokens.index(ele_A[0])
                inx_r = tokens.index(ele_A[-1])
                tu_A = (inx_l, inx_r)
            except:
                tu_A = (0, 0)
            res.append(tu_A)
        return res[0], res[1]
    

    for ind, rows in df_train_filtered.iterrows():
        doc = nlp(rows['Sent'])
        tokens = [token.text.lower() for token in doc]

        tu_A, tu_B = findInx(tokens)
        # ensure left index is the smallest
        if tu_A[0] > tu_B[0]:
            ele1_word_idx = tu_B
            ele2_word_idx = tu_A            
        else:
            ele1_word_idx = tu_A
            ele2_word_idx = tu_B

        ### add the new row
        dict_newrow = dict(rows)
        dict_newrow.update({ 'ele1_word_idx': ele1_word_idx, 
                  'ele2_word_idx': ele2_word_idx, 'tokens': tokens})

        ### new dataframe
        df = df.append(dict_newrow, ignore_index = True)
        
    return df



### purpose: add 3 more columns of SemEval Dataframe to prepare the inputting data for LSTM
### input: The SemEval Dataframe with 3 more columns <'ele1_word_idx', 'ele2_word_idx', 'tokens'>
### output: The SemEval Dataframe with extra columns <'text_between', 'ele1_left_tokens', 'ele2_right_tokens'>

def add3colDf(df_train_filtered):
    # be aware it will be the new dataframe
    new_list = df_train_filtered.columns.to_list()
    t_list = ['text_between', 'ele1_left_tokens', 'ele2_right_tokens']
    new_list.extend(t_list)
    df = pd.DataFrame(columns = new_list)

    for ind, rows in df_train_filtered.iterrows():
        text_between = rows['tokens'][rows['ele1_word_idx'][1]+1: rows['ele2_word_idx'][0]]
        ele1_left_tokens = rows['tokens'][:rows['ele1_word_idx'][0]]
        ele2_right_tokens = rows['tokens'][rows['ele2_word_idx'][1]+1:]

        ### add the new row
        dict_newrow = dict(rows)
        dict_newrow.update({ 'ele1_left_tokens': ele1_left_tokens, 
                  'text_between': text_between, 'ele2_right_tokens': ele2_right_tokens})

        ### new dataframe
        df = df.append(dict_newrow, ignore_index = True)
    return df



# purpose: find only the positive sentences, tag the forward as 1 and backward as 0
# input: the dataframe ready for train 
# output: the dataframe with all positive examples, but tag the forward as 1 and backward as 0
def TagCausalDirec(df):
     
    # only extract the positive examples
    df_dir = df[df['Label']==1]

    for inx, rows in df_dir.iterrows():
        c_single = re.split(' |-', rows['Cause'])[0]
        e_single = re.split(' |-', rows['Effect'])[0]
        if rows['tokens'].index(c_single) > rows['tokens'].index(e_single):
            df_dir.loc[inx, 'Label'] = 0
        
    return df_dir

    
###!!!----------------------------------main functions----------------------------------!!!### 


def main():
    
    print("---------------Procedure 03: classification models--------------")
    
    ### the inputting parameters
    nb_round = sys.argv[1]
    # if this parameter is missing, set the default iterations as 3.
    if nb_round is None:
        nb_round = 3
    else:
        nb_round = int(nb_round)
        
    print("a. The model will be trained for **{}** iterations".format(nb_round))

    
    ### the initialized parameters

    df_res_dev = pd.DataFrame(columns = ['tag', 'Nb:allsamp,predpos,realpos,overlap', 'accuracy', 'precision',
                                        'recall', 'F1'])
    ### get the sentences of semEval
    df_train_semEval = pd.read_pickle(path_here+ "/res/df_train_semEval.pkl")
    df_test_semEval = pd.read_pickle(path_here+ "/res/df_test_semEval.pkl")




    ### train the Logistic Regression Classifier


    # the inputting dataframes
    df_train_semEval.index = range(len(df_train_semEval))
    df_test_semEval.index = range(len(df_train_semEval),len(df_train_semEval)+len(df_test_semEval))
    Y_train_semEval = df_train_semEval['Label'].tolist()
    Y_test_semEval = df_test_semEval['Label'].tolist()


    print("b. start to train Logic Regression Model with **{}** iterations".format(nb_round))
    
    for rd in range(nb_round):

        NameTag = 'LR_Round{}'.format(rd)

        ### try to embedding the sentences by doc2ve
        doc_list = df_train_semEval['Sent'].tolist()
        doc_list.extend(df_test_semEval['Sent'].tolist())
        documents = [TaggedDocument(doc, [i]) for i, doc in enumerate(doc_list)]
        model_doc2vec = Doc2Vec(documents, vector_size=50, window=5, min_count=2, workers=4)

        ### get the sentence embedding 
        wv_semEval_train = GetEmb(df_train_semEval, model_doc2vec)
        ### get the sentence embedding of test set
        wv_semEval_test = GetEmb(df_test_semEval, model_doc2vec)



        ### train the LogisticRegression classifer and evaluate
        X = wv_semEval_train
        y = Y_train_semEval
        clf_lr = LogisticRegression(random_state=0).fit(X, y)
        ### test this classifer
        X_test = wv_semEval_test
        preds_test = clf_lr.predict(X_test)
        probs_test = clf_lr.predict_proba(X_test)
        df_res_dev = df_res_dev.append({'tag': NameTag,
                                        # all samples; predicted postive , real postive, overlap postive
                                        'Nb:allsamp,predpos,realpos,overlap': [len(preds_test), Counter(preds_test)[1], Counter(Y_test_semEval)[1], 
                                        len([i for inx, i in enumerate(preds_test) if i == Y_test_semEval[inx]])],
                                        # metrics values
                                        'accuracy': metrics.accuracy_score(Y_test_semEval, preds_test), 
                                        'precision': metrics.precision_score(Y_test_semEval, preds_test),
                                        'recall': metrics.recall_score(Y_test_semEval, preds_test),
                                        'F1': metrics.f1_score(Y_test_semEval, preds_test),
                                       }, ignore_index=True)

        print("Finished the round **{}** of Logic Regression Model".format(rd))



    ### train the LSTM Classifier

    # the inputting dataframes
    df_train_semEval.index = range(len(df_train_semEval))
    df_test_semEval.index = range(len(df_train_semEval),len(df_train_semEval)+len(df_test_semEval))
    Y_train_semEval = df_train_semEval['Label'].tolist()
    Y_test_semEval = df_test_semEval['Label'].tolist()


    # prepare the dataframes for LSTM
    df_train_semEval2 = addInxcolDf(df_train_semEval)
    df_train_semEval3 = add3colDf(df_train_semEval2)
    df_test_semEval2 = addInxcolDf(df_test_semEval)
    df_test_semEval3 = add3colDf(df_test_semEval2)

    Y_binary = np.array(list(zip([1 if i ==0 else 0 for i in Y_train_semEval], Y_train_semEval)))

    
    print("c . start to train LSTM Model with **{}** iterations".format(nb_round))

    for rd in range(nb_round):

        NameTag = 'LSTM_Round{}'.format(rd)


        ### train the LSTM classifer and evaluate
        X_train = get_feature_arrays(df_train_semEval3)
        model = get_model()
        batch_size = 64
        model.fit(X_train, Y_binary, batch_size=batch_size, epochs=get_n_epochs())

        ### evaluate this classifer
        X_test = get_feature_arrays(df_test_semEval3)
        probs_test = model.predict(X_test)
        preds_test = np.array([1 if r[1] > r[0] else 0 for r in probs_test])

        df_res_dev = df_res_dev.append({'tag': NameTag,
                                        # TODO: add one column : all samples; predicted postive , real postive, overlap postive
                                        'Nb:allsamp,predpos,realpos,overlap': [len(preds_test), Counter(preds_test)[1], Counter(Y_test_semEval)[1], 
                                        len([i for inx, i in enumerate(preds_test) if i == Y_test_semEval[inx]])],
                                        # metrics values
                                        'accuracy': metrics.accuracy_score(Y_test_semEval, preds_test), 
                                        'precision': metrics.precision_score(Y_test_semEval, preds_test),
                                        'recall': metrics.recall_score(Y_test_semEval, preds_test),
                                        'F1': metrics.f1_score(Y_test_semEval, preds_test),
                                       }, ignore_index=True)


        print("Finished the round **{}** of LSTM Model".format(rd))
        
        
        
        print("d . start to train directional LSTM Model with **{}** iterations".format(nb_round))
        
        
        ### train the LSTM classifer twice to get the causal direction prediction
        
        NameTag = 'LSTM_Round{}_Dir'.format(rd)
        
        df_train_semEval4 = TagCausalDirec(df_train_semEval3)
        # only use the test that are tagged as positive by the last LSTM
        df_test_semEval4 = TagCausalDirec(df_test_semEval3[[True if i == 1 else False for i in preds_test]])

        # get the real labels for those dataframe
        Y_train_semEval = np.array(df_train_semEval4['Label'].to_list())
        Y_binary = np.array(list(zip([1 if i ==0 else 0 for i in Y_train_semEval], Y_train_semEval)))
        Y_test_semEval = np.array(df_test_semEval4['Label'].to_list())



        ### train the LogisticRegression classifer and evaluate
        X_train = get_feature_arrays(df_train_semEval4)
        model = get_model()
        batch_size = 64
        model.fit(X_train, Y_binary, batch_size=batch_size, epochs=get_n_epochs())

        ### evaluate this classifer
        X_test = get_feature_arrays(df_test_semEval4)
        probs_test = model.predict(X_test)
        preds_test = np.array([1 if r[1] > r[0] else 0 for r in probs_test])

        df_res_dev = df_res_dev.append({'tag': NameTag,
                                        # TODO: add one column : all samples; predicted postive , real postive, overlap postive
                                        'Nb:allsamp,predpos,realpos,overlap': [len(preds_test), Counter(preds_test)[1], Counter(Y_test_semEval)[1], 
                                        len([i for inx, i in enumerate(preds_test) if i == Y_test_semEval[inx]])],
                                        # metrics values
                                        'accuracy': metrics.accuracy_score(Y_test_semEval, preds_test), 
                                        'precision': metrics.precision_score(Y_test_semEval, preds_test),
                                        'recall': metrics.recall_score(Y_test_semEval, preds_test),
                                        'F1': metrics.f1_score(Y_test_semEval, preds_test),
                                       }, ignore_index=True)
        
        
        ### present the wrong calssification results
        
        print("-------------the prediction results-------------")
        ### the false sentences that are predcited as postive 
        for inx, rows in df_test_semEval4.reset_index().iterrows():
            if rows['Label'] == 0 and preds_test[inx] == 1:
                print("----------------------")
                print("ground truth: ", rows['Cause'], " --> ", rows['Effect'])
                print("predict: ", rows['Effect'], " --> ", rows['Cause'])
                print(rows['Sent'])

    
    # save results to disk
    df_res_dev.to_csv(path_here+ "/res/df_res_dev_iter{}.csv".format(nb_round))
    df_res_dev.to_pickle(path_here+ "/res/df_res_dev_iter{}.pkl".format(nb_round))
    print("The evaluation results are saved to -->  ./res/df_res_dev_iter{}.pkl".format(nb_round))
    


  
    
if __name__ == "__main__":
    main()






















