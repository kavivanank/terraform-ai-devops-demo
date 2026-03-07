variable "aws_region" {
  default = "us-east-1"
}

variable "instance_type" {
  default = "t3.kutty"
}

variable "ami_id" {
  description = "AMI for EC2 instance"
}
