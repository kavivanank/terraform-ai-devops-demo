variable "aws_region" {
  default = "us-east-1"
}

variable "instance_type" {
  default = "m.large"
}

variable "ami_id" {
  description = "AMI for EC2 instance"
}
