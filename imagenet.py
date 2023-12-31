# -*- coding: utf-8 -*-
"""Lecture 10 - DL.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1zXbjz9eZ0Z41EkjynJhA2bz1JfuHzlRD
"""

!apt-get install openjdk-8-jdk-headless -qq > /dev/null
!wget -q https://downloads.apache.org/spark/spark-3.1.1/spark-3.1.1-bin-hadoop3.2.tgz
!tar xvzf spark-3.1.1-bin-hadoop3.2.tgz
!pip install -q findspark
!pip install pyarrow
try:
  # %tensorflow_version only exists in Colab.
  !pip install --disable-pip-version-check install tf-nightly
except Exception:
  pass

import os
os.environ["JAVA_HOME"] = "/usr/lib/jvm/java-8-openjdk-amd64"
os.environ["SPARK_HOME"] = "/content/spark-3.1.1-bin-hadoop3.2"

import findspark
findspark.init()
from pyspark.sql import SparkSession
spark = SparkSession.builder.master("local[*]").getOrCreate()

from __future__ import absolute_import, division, print_function, unicode_literals

import tensorflow as tf

import pathlib
data_dir = tf.keras.utils.get_file(origin='https://storage.googleapis.com/download.tensorflow.org/example_images/flower_photos.tgz',
                                         fname='flower_photos', untar=True)

images = spark.read.format("binaryFile").option("recursiveFileLookup", "true").option("pathGlobFilter", "*.jpg").load(data_dir)

from pyspark.sql.functions import col, pandas_udf, regexp_extract

def extract_label(path_col):
  """Extract label from file path using built-in SQL functions."""
  return regexp_extract(path_col, "flower_photos/([^/]+)", 1)

def extract_size(content):
  """Extract image size from its raw content."""
  image = Image.open(io.BytesIO(content))
  return image.size

@pandas_udf("width: int, height: int")
def extract_size_udf(content_series):
  sizes = content_series.apply(extract_size)
  return pd.DataFrame(list(sizes))

df = images.select(
  col("path"),
  col("modificationTime"),
  extract_label(col("path")).alias("label"),
  extract_size_udf(col("content")).alias("size"),
  col("content"))

import io

from tensorflow.keras.applications.imagenet_utils import decode_predictions
import pandas as pd
from pyspark.sql.functions import col, pandas_udf, PandasUDFType
import torch
from torch.utils.data import Dataset, DataLoader
from torchvision import models, transforms
from PIL import Image

class ImageNetDataset(Dataset):
  """
  Converts image contents into a PyTorch Dataset with standard ImageNet preprocessing.
  """
  def __init__(self, contents):
    self.contents = contents

  def __len__(self):
    return len(self.contents)

  def __getitem__(self, index):
    return self._preprocess(self.contents[index])

  def _preprocess(self, content):
    """
    Preprocesses the input image content using standard ImageNet normalization.

    See https://pytorch.org/docs/stable/torchvision/models.html.
    """
    image = Image.open(io.BytesIO(content))
    transform = transforms.Compose([
      transforms.Resize(256),
      transforms.CenterCrop(224),
      transforms.ToTensor(),
      transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    return transform(image)

def imagenet_model_udf(model_fn):
  """
  Wraps an ImageNet model into a Pandas UDF that makes predictions.

  You might consider the following customizations for your own use case:
    - Tune DataLoader's batch_size and num_workers for better performance.
    - Use GPU for acceleration.
    - Change prediction types.
  """
  def predict(content_series_iter):
    model = model_fn()
    model.eval()
    for content_series in content_series_iter:
      dataset = ImageNetDataset(list(content_series))
      loader = DataLoader(dataset, batch_size=64)
      with torch.no_grad():
        for image_batch in loader:
          predictions = model(image_batch).numpy()
          predicted_labels = [x[0] for x in decode_predictions(predictions, top=1)]
          # print(predicted_labels)
          # break
          yield pd.DataFrame(predicted_labels)
  return_type = "class: string, desc: string, score:float"
  return pandas_udf(return_type, PandasUDFType.SCALAR_ITER)(predict)

mobilenet_v2_udf = imagenet_model_udf(lambda: models.mobilenet_v2(pretrained=True))

#images = table("ml_tmp.flowers")
#predictions = images.withColumn("prediction", mobilenet_v2_udf(col("content")))

predictions = df.withColumn("prediction", mobilenet_v2_udf(col("content")))
display(predictions.select(col("path"), col("prediction")).limit(5))

predictions.select(col("prediction")).show(5)

predictions.select(col("label"),col("prediction")).show(5)
